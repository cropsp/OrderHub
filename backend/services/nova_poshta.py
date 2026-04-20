"""
OrderHub CRM — Nova Poshta Service
"""

from datetime import datetime

import httpx

NP_API_URL = "https://api.novaposhta.ua/v2.0/json/"

class NovaPoshtaClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def _post(self, model_name: str, called_method: str, method_properties: dict) -> dict:
        payload = {
            "apiKey": self.api_key,
            "modelName": model_name,
            "calledMethod": called_method,
            "methodProperties": method_properties
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(NP_API_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                errors = data.get("errors", [])
                raise Exception(f"Nova Poshta API Error: {errors}")
            return data["data"]

    async def get_cities(self, query: str = "") -> list:
        props = {"FindByString": query} if query else {}
        return await self._post("Address", "getCities", props)

    async def get_warehouses(self, city_ref: str, query: str = "") -> list:
        props = {"CityRef": city_ref}
        if query:
            props["FindByString"] = query
        return await self._post("Address", "getWarehouses", props)

    async def create_internet_document(self, props: dict) -> dict:
        """
        Create a TTN (waybill).
        Expects properties like PayerType, PaymentMethod, DateTime, CargoType, Weight, etc.
        """
        data = await self._post("InternetDocument", "save", props)
        if not data:
            raise Exception("Failed to create InternetDocument: empty response")
        return data[0]

# --- Helper functions for the CRM ---

def build_ttn_payload(
    sender_city_ref: str,
    sender_warehouse_ref: str,
    sender_phone: str,
    sender_name: str,
    recipient_city_ref: str,
    recipient_warehouse_ref: str,
    recipient_phone: str,
    recipient_name: str,
    weight: float,
    description: str,
    cost: float,
) -> dict:
    # Separate names (NP expects Last/First/Middle)
    names = recipient_name.strip().split(" ", 2)
    recipient_last = names[0] if len(names) > 0 else "Unknown"
    recipient_first = names[1] if len(names) > 1 else "Unknown"
    recipient_middle = names[2] if len(names) > 2 else ""

    senders = sender_name.strip().split(" ", 2)
    sender_last = senders[0] if len(senders) > 0 else "Unknown"
    sender_first = senders[1] if len(senders) > 1 else "Unknown"
    sender_middle = senders[2] if len(senders) > 2 else ""

    return {
        "PayerType": "Sender",
        "PaymentMethod": "Cash",
        "DateTime": datetime.now().strftime("%d.%m.%Y"),
        "CargoType": "Parcel",
        "VolumeGeneral": str(0.01),  # Default volume
        "Weight": str(weight),
        "ServiceType": "WarehouseWarehouse",
        "SeatsAmount": "1",
        "Description": description,
        "Cost": str(cost),
        "CitySender": sender_city_ref,
        "Sender": sender_last,  # Actually needs Sender ref, but this is simplified for now
        "SenderAddress": sender_warehouse_ref,
        "ContactSender": sender_phone,
        "SendersPhone": sender_phone,
        "CityRecipient": recipient_city_ref,
        "Recipient": f"{recipient_last} {recipient_first} {recipient_middle}".strip(),
        "RecipientAddress": recipient_warehouse_ref,
        "ContactRecipient": recipient_phone,
        "RecipientsPhone": recipient_phone,
    }
