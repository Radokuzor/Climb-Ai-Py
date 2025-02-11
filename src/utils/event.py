from src.db.database import db
from src.utils.helper_functions import (
    convert_central_time_to_utc, add_minutes_to_iso_string,
    format_to_readable_date
)


async def create_or_update_event(task_data, user_id, from_phone_number):
    events_collection = db.collection("events")
    start = convert_central_time_to_utc(task_data["start"])
    end = task_data.get("end", add_minutes_to_iso_string(task_data["start"], task_data.get("duration", 60)))

    existing_event_query = events_collection.where("start", "==", start).where("ownerId", "==", user_id).stream()

    existing_event = None
    async for doc in existing_event_query:
        existing_event = doc

    if existing_event:
        print(f"Event already exists with ID: {existing_event.id}, updating the event...")
        existing_event.reference.update({
            "title": task_data["title"] if "title" in task_data else existing_event.get("title"),
            "start": start,
            "end": end if end else existing_event.get("end"),
        })
        return f"Event with start time {format_to_readable_date(task_data['start'])} CST has been updated successfully."
    else:
        print(f"No event found with start time: {start} and ownerId: {user_id}. Creating a new event...")
        events_collection.add({
            "title": task_data["title"],
            "start": start,
            "end": end,
            "ownerId": user_id,
        })
        
        # Delete conversation for the user
        users_collection = db.collection("users")
        user_query = users_collection.where("phoneNumber", "==", from_phone_number).stream()
        
        async for user_doc in user_query:
            conversation_ref = user_doc.reference.collection("conversation")
            conversation_docs = conversation_ref.stream()
            
            async for doc in conversation_docs:
                doc.reference.delete()

            print("All conversation documents deleted.")

        return f"New event with start time {format_to_readable_date(start)} has been created successfully."
