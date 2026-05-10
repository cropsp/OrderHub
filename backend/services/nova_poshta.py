"""
OrderHub CRM — Nova Poshta Service
"""

from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import logging

logger = logging.getLogger(__name__)

NP_API_URL = "https://api.novaposhta.ua/v2.0/json/"

class NovaPoshtaAPIError(Exception):
    """Raised when Nova Poshta API returns success: false. Never retryable."""
    pass

class NovaPoshtaClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def _post(self, model_name: str, called_method: str, method_properties: dict) -> dict:
        payload = {
            "apiKey": self.api_key,
            "modelName": model_name,
            "calledMethod": called_method,
            "methodProperties": method_properties
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(NP_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                errors = data.get("errors", [])
                error_msg = f"[NP API] Error: {', '.join(errors)}"
                logger.error(error_msg)
                raise NovaPoshtaAPIError(error_msg)
            return data.get("data", [])

    async def get_cities(self, query: str = "") -> list:
        props = {"FindByString": query} if query else {}
        return await self._post("Address", "getCities", props)

    async def get_warehouses(self, city_ref: str, query: str = "") -> list:
        props = {"CityRef": city_ref}
        if query:
            props["FindByString"] = query
        return await self._post("Address", "getWarehouses", props)

    async def create_internet_document(self, props: dict) -> dict:
        """Create a TTN (waybill)."""
        data = await self._post("InternetDocument", "save", props)
        if not data:
            raise Exception("[NP API] Failed to create InternetDocument: empty response")
        return data[0]

    async def get_counterparties(self, counterparty_property: str = "Recipient", find_by_string: str = "") -> list:
        """Get counterparties (Sender/Recipient)."""
        props = {"CounterpartyProperty": counterparty_property}
        if find_by_string:
            props["FindByString"] = find_by_string
        return await self._post("Counterparty", "getCounterparties", props)

    async def create_counterparty(self, first_name: str, middle_name: str, last_name: str, phone: str, counterparty_property: str = "Recipient") -> dict:
        """Create a new counterparty."""
        props = {
            "FirstName": first_name,
            "MiddleName": middle_name,
            "LastName": last_name,
            "Phone": phone,
            "Email": "",
            "CounterpartyType": "PrivatePerson",
            "CounterpartyProperty": counterparty_property
        }
        data = await self._post("Counterparty", "save", props)
        if not data:
            raise Exception("[NP API] Failed to create counterparty")
        return data[0]

    async def get_contact_persons(self, counterparty_ref: str) -> list:
        """Get contact persons for a counterparty.

        Calls NP API method `Counterparty.getCounterpartyContactPersons`,
        which works for both PrivatePerson and Organization API keys.
        The earlier name `getContactPersons` (no `Counterparty` prefix)
        returned "Method not found" for PrivatePerson keys because NP
        internally redirected the call to a non-existent
        `CounterpartyGeneral_getContactPersons` model. Verified via
        direct curl against api.novaposhta.ua on 2026-05-10:
        `getCounterpartyContactPersons` returns "Ref is not specified"
        (i.e. method exists, parameter validation reachable) for a
        PrivatePerson key, while `getContactPersons` returns "Method
        not found" — proof of the rename being the correct fix.
        """
        return await self._post("Counterparty", "getCounterpartyContactPersons", {"Ref": counterparty_ref})

    async def delete_internet_document(self, document_refs: str) -> bool:
        """Delete an existing waybill (TTN)."""
        await self._post("InternetDocument", "delete", {"DocumentRefs": document_refs})
        return True


