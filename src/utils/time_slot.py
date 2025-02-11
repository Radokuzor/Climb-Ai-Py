from datetime import datetime, timedelta, timezone
from src.db.database import db
from collections import defaultdict

def find_available_time_slots(events, number_of_slots=5):
    """Find available time slots based on existing event schedules."""

    # Function to parse Firestore timestamps
    def parse_time(time_str):
        try:
            return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")  # ISO 8601 format
        except ValueError:
            return datetime.strptime(time_str, "%m/%d/%Y, %H:%M")  # Fallback format

    # Group events by owner
    events_by_owner = defaultdict(list)

    for event in events:
        owner = event.get("ownerId")  # Ensure ownerId exists in event
        if owner:
            events_by_owner[owner].append({
                "start": parse_time(event["start"]),
                "end": parse_time(event["end"]),
            })

    # Sort events for each owner
    for owner in events_by_owner:
        events_by_owner[owner].sort(key=lambda e: e["start"])

    # Define business hours (9 AM - 6 PM) and slot duration (30 mins)
    business_hour_start = 9  # 9 AM
    business_hour_end = 18  # 6 PM
    slot_duration = timedelta(minutes=30)

    # Get today's date and next 7 days
    today = datetime.now()  # Ensure we use UTC time
    next_week = today + timedelta(days=7)

    available_slots = []

    # Iterate through each day
    current_date = today
    while current_date <= next_week:
        # Skip weekends (Saturday=5, Sunday=6)
        if current_date.weekday() in [5, 6]:  
            current_date += timedelta(days=1)
            continue

        # Iterate for each half-hour slot
        for hour in range(business_hour_start, business_hour_end):
            for minute in [0, 30]:
                slot_start = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # Skip slots in the past
                if slot_start < today:
                    continue

                slot_end = slot_start + slot_duration

                # Check if this slot is available for any owner
                is_slot_available = any(
                    not any(
                        (slot_start >= event["start"] and slot_start < event["end"]) or
                        (slot_end > event["start"] and slot_end <= event["end"]) or
                        (slot_start <= event["start"] and slot_end >= event["end"])
                        for event in owner_events
                    )
                    for owner_events in events_by_owner.values()
                )

                if is_slot_available:
                    available_slots.append({
                        "start": slot_start.strftime("%d-%m-%Y, %H:%M"),  # Keep consistent Firestore format
                        "end": slot_end.strftime("%d-%m-%Y, %H:%M"),
                    })

                    # Break if we have enough slots
                    if len(available_slots) >= number_of_slots:
                        return available_slots

        current_date += timedelta(days=1)

    return available_slots

async def get_available_slots(company_id: str):
    """Fetch available time slots for a given company in the next 7 days."""
    
    now = datetime.now()
    seven_days_later = now + timedelta(days=7)

    print(f"Current Time: {now.isoformat()}")

    try:
        events_ref = db.collection("events")
        query = (
            events_ref
            .where("createdBy", "==", company_id)
            .where("start", ">=", now.isoformat())
            .where("start", "<=", seven_days_later.isoformat())
        )

        events_snapshot = query.get()

        events = []
        if events_snapshot:
            events = [doc.to_dict() for doc in events_snapshot]
            print("Fetched Events:", events)

        return find_available_time_slots(events)
    
    except Exception as e:
        print("Error fetching events:", str(e))
        return {"error": "Failed to fetch available slots"}