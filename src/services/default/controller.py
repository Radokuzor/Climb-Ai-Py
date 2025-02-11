from src.db.database import db
from src.utils.time_slot import get_available_slots

import logging


logger = logging.getLogger(__name__)

cached_availability = None


class DefaultController:
    
    @classmethod
    async def get_company_availability(cls,to_phone_number: str, force_fetch: bool = False):
        """Fetch company availability based on phone number."""
        global cached_availability

        # Use cached data if available and no forceFetch
        if cached_availability and not force_fetch:
            print("Returning cached availability")
            return cached_availability

        try:
            # Step 1: Find the company by phone number
            company_ref = db.collection("companies")

            queries = [
                company_ref.where("liTextNumber", "==", to_phone_number),
                company_ref.where("liPhoneNumber", "==", to_phone_number),
                company_ref.where("agentFAQNumber", "==", to_phone_number),
            ]

            company_snapshot = None
            for query in queries:
                snapshot = query.get()
                if snapshot and snapshot:
                    company_snapshot = snapshot
                    break

            if company_snapshot:
                print(f"Company found with phone number: {to_phone_number}")
                company_doc = company_snapshot[0]  # Get the first matching company document
                company_data = company_doc.to_dict()
                print("Company Data:", company_data)

                company_id = company_data.get("ownerId")
                print("Company ID:", company_id)

                return await get_available_slots(company_id)

            print("No company found for the provided phone number.")
            return {"message": "Company not found"}

        except Exception as e:
            print("Error fetching company availability:", str(e))
            return {"error": "Failed to fetch company availability"}
