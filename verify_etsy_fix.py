import asyncio
import uuid
import io
from unittest.mock import AsyncMock, MagicMock
from services.etsy_parser import parse_etsy_csv
from models.shop import Shop

CSV_DATA = """ "Sale Date","Item Name",Buyer,Quantity,Price,"Coupon Code","Coupon Details","Discount Amount","Shipping Discount","Order Shipping","Order Sales Tax","Item Total",Currency,"Transaction ID","Listing ID","Date Paid","Date Shipped","Ship Name","Ship Address1","Ship Address2","Ship City","Ship State","Ship Zipcode","Ship Country","Order ID",Variations,"Order Type","Listings Type","Payment Type","InPerson Discount","InPerson Location","VAT Paid by Buyer",SKU
04/20/26,"Personalized Bat ID Card Holder: Handcrafted Leather Superhero Wallet","Marty (gk721kjqc1e5aoop)",1,38.99,,,0.00,0.00,8,0,38.99,USD,5034190758,4347345198,04/20/2026,,"Martha Giretti","57 S 3rd St",,Brooklyn,NY,11249,"United States",4037941285,"Color:Black,Packaging:With Gift Box",online,listing,online_cc,,,0,"bat id holder book"
04/17/26,"Personalized Bat ID Card Holder: Handcrafted Leather Superhero Wallet","Lynette Hunt (vfoaua6j)",1,29.99,YOURFAVE,"YOURFAVE - % off",3.00,0.00,8,0,29.99,USD,5031352290,4347345198,04/17/2026,04/20/2026,"Lynette Hunt","224 Jones St",,"Siloam Springs",AR,72761,"United States",4035389345,"Color:Black,Packaging:Standart",online,listing,online_cc,,,0,"bat id holder book"
""".strip()

async def test_parser():
    # Mock DB and Shop
    db = AsyncMock()
    # Mock duplicate check to say it's NOT a duplicate
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    # Mock upsert_customer
    from services import etsy_parser
    etsy_parser.upsert_customer = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    
    shop = Shop(id=uuid.uuid4(), name="Etsy Shop")
    user_id = uuid.uuid4()
    
    # Run parser
    result = await parse_etsy_csv(db, shop, CSV_DATA.encode('utf-8'), user_id)
    
    print(f"Imported: {result.imported}")
    print(f"Skipped: {result.skipped}")
    print(f"Errors: {result.errors}")
    
    if result.imported == 2 and not result.errors:
        print("\nVerification SUCCESS: Parser correctly handled Order ID and Item Total.")
    else:
        print("\nVerification FAILED.")

if __name__ == "__main__":
    asyncio.run(test_parser())
