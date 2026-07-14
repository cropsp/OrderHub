"""PC-F-1 — product image: storage, validation, endpoints, Shopify pull.

Follows the repo's established test style: router functions are awaited directly
with mocked dependencies (no TestClient / conftest fixtures exist — see
test_products_platform_gate.py). Storage tests monkeypatch the module-level
file_storage.UPLOADS_DIR, which is frozen at import (file_storage.py:13), so
patching the env var alone would have no effect.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from models.product import Product
from models.shop import ShopPlatform
from routers.products import (
    _project_product,
    delete_product_image,
    get_product_image,
    pull_product_image_from_shopify,
    upload_product_image,
)
from services import file_storage
from services.file_storage import (
    FileTooLargeError,
    save_file,
    save_product_image,
    sniff_image_mime,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
HTML_BYTES = b"<html><script>alert(1)</script></html>"


def _upload(content: bytes, filename: str = "pic.png") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def _product(image_path=None, external_ref=None, shop_id=None) -> Product:
    now = datetime.now(timezone.utc)
    p = Product(
        id=uuid.uuid4(),
        shop_id=shop_id or uuid.uuid4(),
        title="Leather Wallet",
        description=None,
        external_ref=external_ref,
        image_path=image_path,
        is_active=True,
    )
    p.created_at = now
    p.updated_at = now
    p.variants = []
    return p


def _patch_uploads(monkeypatch, tmp_path) -> Path:
    monkeypatch.setattr(file_storage, "UPLOADS_DIR", tmp_path)
    return tmp_path


@contextmanager
def _mock_catalog(product):
    """Patch CatalogService so _load_product_or_404 returns `product`."""
    with patch("routers.products.CatalogService") as MockSvc:
        MockSvc.return_value.get_product = AsyncMock(return_value=product)
        yield MockSvc


# --- sniffing -------------------------------------------------------------


def test_sniff_recognises_allowed_types():
    assert sniff_image_mime(PNG_BYTES) == "image/png"
    assert sniff_image_mime(JPEG_BYTES) == "image/jpeg"
    assert sniff_image_mime(WEBP_BYTES) == "image/webp"


def test_sniff_rejects_html_and_empty():
    assert sniff_image_mime(HTML_BYTES) is None
    assert sniff_image_mime(b"") is None


# --- storage --------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_product_image_writes_under_products_subdir(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    pid = uuid.uuid4()

    rel, size = await save_product_image(_upload(PNG_BYTES), pid, "png")

    assert rel.startswith(f"products/{pid}/")
    assert rel.endswith(".png")
    assert size == len(PNG_BYTES)
    assert (uploads / rel).read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_save_product_image_rejects_oversize_and_leaves_no_partial(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    monkeypatch.setattr(file_storage, "PRODUCT_IMAGE_MAX_BYTES", 128)
    pid = uuid.uuid4()

    with pytest.raises(FileTooLargeError):
        await save_product_image(_upload(b"\x89PNG\r\n\x1a\n" + b"x" * 500), pid, "png")

    product_dir = uploads / "products" / str(pid)
    assert list(product_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_save_file_order_path_unchanged(monkeypatch, tmp_path):
    """OQ-1 regression guard: extracting _stream_to_disk must not alter the
    order-attachment save path."""
    uploads = _patch_uploads(monkeypatch, tmp_path)
    order_id = uuid.uuid4()

    rel, size = await save_file(_upload(b"hello", filename="brief.pdf"), order_id)

    assert rel.startswith(f"{order_id}/")
    assert rel.endswith("_brief.pdf")
    assert size == 5
    assert (uploads / rel).read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_save_file_still_enforces_max_size(monkeypatch, tmp_path):
    _patch_uploads(monkeypatch, tmp_path)
    with pytest.raises(FileTooLargeError):
        await save_file(_upload(b"x" * 100, filename="big.bin"), uuid.uuid4(), max_size=10)


# --- projection -----------------------------------------------------------


def test_project_product_image_url_null_without_image():
    assert _project_product(_product()).image_url is None


def test_project_product_image_url_points_at_route_with_image():
    p = _product(image_path="products/x/y.png")
    assert _project_product(p).image_url == f"/api/products/{p.id}/image"


# --- upload / delete / serve ---------------------------------------------


@pytest.mark.asyncio
async def test_upload_sets_image_path(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    product = _product()
    db = AsyncMock()

    with _mock_catalog(product):
        result = await upload_product_image(
            id=product.id, file=_upload(PNG_BYTES), db=db, user=MagicMock()
        )

    assert product.image_path.startswith(f"products/{product.id}/")
    assert result.image_url == f"/api/products/{product.id}/image"
    assert (uploads / product.image_path).read_bytes() == PNG_BYTES
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upload_rejects_non_image_with_415(monkeypatch, tmp_path):
    _patch_uploads(monkeypatch, tmp_path)
    product = _product()

    with _mock_catalog(product):
        with pytest.raises(HTTPException) as exc:
            await upload_product_image(
                id=product.id,
                file=_upload(HTML_BYTES, filename="evil.png"),
                db=AsyncMock(),
                user=MagicMock(),
            )

    assert exc.value.status_code == 415
    assert product.image_path is None


@pytest.mark.asyncio
async def test_replace_deletes_the_previous_file(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    product = _product()
    db = AsyncMock()

    with _mock_catalog(product):
        await upload_product_image(
            id=product.id, file=_upload(PNG_BYTES), db=db, user=MagicMock()
        )
        first_path = product.image_path
        await upload_product_image(
            id=product.id, file=_upload(JPEG_BYTES, filename="new.jpg"), db=db, user=MagicMock()
        )

    assert product.image_path != first_path
    assert product.image_path.endswith(".jpg")
    assert not (uploads / first_path).exists()  # no orphan left behind
    assert (uploads / product.image_path).exists()


@pytest.mark.asyncio
async def test_delete_nulls_column_and_removes_file(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    product = _product()
    db = AsyncMock()

    with _mock_catalog(product):
        await upload_product_image(
            id=product.id, file=_upload(PNG_BYTES), db=db, user=MagicMock()
        )
        saved = uploads / product.image_path
        await delete_product_image(id=product.id, db=db, user=MagicMock())

    assert product.image_path is None
    assert not saved.exists()


@pytest.mark.asyncio
async def test_delete_is_idempotent_when_no_image():
    product = _product()
    with _mock_catalog(product):
        await delete_product_image(id=product.id, db=AsyncMock(), user=MagicMock())
    assert product.image_path is None


@pytest.mark.asyncio
async def test_serve_404s_when_no_image():
    product = _product()
    with _mock_catalog(product):
        with pytest.raises(HTTPException) as exc:
            await get_product_image(id=product.id, db=AsyncMock(), user=MagicMock())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_serve_returns_bytes_with_sniffed_content_type(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    product = _product()
    db = AsyncMock()

    with _mock_catalog(product):
        await upload_product_image(
            id=product.id, file=_upload(WEBP_BYTES, filename="x.bin"), db=db, user=MagicMock()
        )
        response = await get_product_image(id=product.id, db=db, user=MagicMock())

    assert response.media_type == "image/webp"
    assert Path(response.path).read_bytes() == WEBP_BYTES


# --- Shopify pull ---------------------------------------------------------


class _FakeStreamResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    async def aiter_bytes(self, chunk_size=None):
        yield self._content


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient supporting `async with .stream()`."""

    content = PNG_BYTES

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url):
        content = self.content

        class _Ctx:
            async def __aenter__(self):
                return _FakeStreamResponse(content)

            async def __aexit__(self, *args):
                return False

        return _Ctx()


def _shopify_shop():
    shop = MagicMock()
    shop.platform = ShopPlatform.SHOPIFY
    shop.shopify_store_url = "https://lamamarka.myshopify.com"
    shop.shopify_access_token_encrypted = "encrypted-token"
    return shop


@pytest.mark.asyncio
async def test_pull_from_shopify_rewraps_gid_and_sets_image(monkeypatch, tmp_path):
    uploads = _patch_uploads(monkeypatch, tmp_path)
    product = _product(external_ref="12345")
    db = AsyncMock()
    db.get = AsyncMock(return_value=_shopify_shop())
    graphql = AsyncMock(return_value={"product": {"featuredImage": {"url": "https://cdn/x.png"}}})

    with _mock_catalog(product), \
            patch("routers.products.decrypt_value", return_value="tok"), \
            patch("routers.products.call_shopify_graphql", graphql), \
            patch("routers.products.httpx.AsyncClient", _FakeAsyncClient):
        result = await pull_product_image_from_shopify(
            id=product.id, db=db, user=MagicMock()
        )

    # external_ref stores the numeric id — it must be re-wrapped into a GID.
    _args, kwargs = graphql.call_args
    variables = _args[3] if len(_args) > 3 else kwargs["variables"]
    assert variables == {"id": "gid://shopify/Product/12345"}

    assert product.image_path.endswith(".png")
    assert (uploads / product.image_path).read_bytes() == PNG_BYTES
    assert result.image_url == f"/api/products/{product.id}/image"


@pytest.mark.asyncio
async def test_pull_from_shopify_409_on_non_shopify_shop():
    product = _product(external_ref="12345")
    etsy = MagicMock()
    etsy.platform = ShopPlatform.ETSY
    db = AsyncMock()
    db.get = AsyncMock(return_value=etsy)

    with _mock_catalog(product):
        with pytest.raises(HTTPException) as exc:
            await pull_product_image_from_shopify(id=product.id, db=db, user=MagicMock())

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pull_from_shopify_409_without_external_ref():
    product = _product(external_ref=None)
    db = AsyncMock()
    db.get = AsyncMock(return_value=_shopify_shop())

    with _mock_catalog(product):
        with pytest.raises(HTTPException) as exc:
            await pull_product_image_from_shopify(id=product.id, db=db, user=MagicMock())

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_pull_from_shopify_404_when_listing_has_no_featured_image():
    product = _product(external_ref="12345")
    db = AsyncMock()
    db.get = AsyncMock(return_value=_shopify_shop())

    with _mock_catalog(product), \
            patch("routers.products.decrypt_value", return_value="tok"), \
            patch("routers.products.call_shopify_graphql",
                  AsyncMock(return_value={"product": {"featuredImage": None}})):
        with pytest.raises(HTTPException) as exc:
            await pull_product_image_from_shopify(id=product.id, db=db, user=MagicMock())

    assert exc.value.status_code == 404
    assert product.image_path is None


@pytest.mark.asyncio
async def test_pull_from_shopify_415_when_remote_bytes_are_not_an_image(monkeypatch, tmp_path):
    """The remote URL is untrusted input — it gets the same sniff as an upload."""
    _patch_uploads(monkeypatch, tmp_path)
    product = _product(external_ref="12345")
    db = AsyncMock()
    db.get = AsyncMock(return_value=_shopify_shop())

    class _HtmlClient(_FakeAsyncClient):
        content = HTML_BYTES

    with _mock_catalog(product), \
            patch("routers.products.decrypt_value", return_value="tok"), \
            patch("routers.products.call_shopify_graphql",
                  AsyncMock(return_value={"product": {"featuredImage": {"url": "https://cdn/x"}}})), \
            patch("routers.products.httpx.AsyncClient", _HtmlClient):
        with pytest.raises(HTTPException) as exc:
            await pull_product_image_from_shopify(id=product.id, db=db, user=MagicMock())

    assert exc.value.status_code == 415
    assert product.image_path is None
