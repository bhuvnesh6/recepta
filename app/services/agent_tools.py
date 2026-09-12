"""
Backend tools the AI agent can invoke. The LLM can *request* a tool call,
but only this module ever performs the actual database write - the model
never modifies data directly. Every function is scoped to the calling
agent's organization_id.

Every function accepts an optional `db=` parameter. When omitted it falls
back to get_db() (the normal case - inside a Flask request). The voice
streaming pipeline (voice_stream_service.py) runs its LLM/TTS loops on
background threads with no Flask request context, so it passes its own
long-lived pymongo Database handle explicitly instead - pymongo Database/
Collection objects are documented as thread-safe, so sharing one handle
across those threads is correct and avoids reopening a Mongo connection
per call.
"""
from datetime import datetime, timedelta, timezone
from app.extensions import get_db
from app.models import build_lead, build_appointment, now
from app.services import rag_service, assignment_service, notification_service, usage_service
from bson import ObjectId


def search_knowledge(organization_id, agent_id, query, top_k=5, db=None):
    return rag_service.retrieve(organization_id, agent_id, query, top_k=top_k, db=db)


def capture_lead(organization_id, agent_id, conversation_id, name=None, email=None,
                  phone=None, requirement=None, location=None, budget=None, is_test=False, db=None):
    db = db or get_db()
    lead_doc = build_lead(
        organization_id, agent_id, name=name, email=email, phone=phone,
        requirement=requirement, location=location, budget=budget,
        conversation_id=conversation_id, is_test=is_test,
    )
    lead_doc["qualification"] = "qualified" if (name and (email or phone)) else "unqualified"
    result = db.leads.insert_one(lead_doc)
    lead_doc["_id"] = result.inserted_id
    db.conversations.update_one({"_id": ObjectId(conversation_id)}, {"$set": {"lead_id": str(result.inserted_id)}})

    if not is_test:
        assignee = assignment_service.auto_assign(organization_id, lead_doc, db=db)
        if assignee:
            db.leads.update_one({"_id": result.inserted_id}, {"$set": {"assigned_to": assignee}})
        notification_service.notify_new_lead(organization_id, lead_doc, assignee, db=db)
        usage_service.track(organization_id, agent_id, "leads_captured", 1, db=db)
    return str(result.inserted_id)


def update_lead(organization_id, lead_id, db=None, **fields):
    db = db or get_db()
    fields["updated_at"] = now()
    db.leads.update_one(
        {"_id": ObjectId(lead_id), "organization_id": organization_id},
        {"$set": fields},
    )
    return get_lead(organization_id, lead_id, db=db)


def get_lead(organization_id, lead_id, db=None):
    db = db or get_db()
    return db.leads.find_one({"_id": ObjectId(lead_id), "organization_id": organization_id})


def check_availability(organization_id, agent_id, date_str, db=None):
    """Very simple slot generator for MVP: 9am-5pm, 1hr slots, minus already-booked ones.
    Swap for Google Calendar / Outlook / Calendly integration later without
    changing the tool's signature."""
    db = db or get_db()
    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return []
    slots = []
    for hour in range(9, 17):
        start = day.replace(hour=hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        clash = db.appointments.find_one({
            "organization_id": organization_id,
            "agent_id": agent_id,
            "status": "scheduled",
            "start_time": {"$lt": end},
            "end_time": {"$gt": start},
        })
        if not clash:
            slots.append(start.strftime("%Y-%m-%d %H:%M"))
    return slots


def book_appointment(organization_id, agent_id, lead_id, start_time_str, kind="appointment",
                      address=None, notes=None, db=None):
    db = db or get_db()
    start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    clash = db.appointments.find_one({
        "organization_id": organization_id, "agent_id": agent_id, "status": "scheduled",
        "start_time": {"$lt": end}, "end_time": {"$gt": start},
    })
    if clash:
        return {"success": False, "error": "slot_unavailable"}
    doc = build_appointment(organization_id, agent_id, lead_id, kind, start, end, address, notes)
    result = db.appointments.insert_one(doc)
    doc["_id"] = result.inserted_id
    db.leads.update_one(
        {"_id": ObjectId(lead_id), "organization_id": organization_id},
        {"$set": {"status": "Site Visit" if kind == "site_visit" else "Appointment", "updated_at": now()}},
    )
    notification_service.notify_appointment_booked(organization_id, doc, db=db)
    return {"success": True, "appointment_id": str(result.inserted_id), "start_time": start_time_str}


def request_site_visit(organization_id, agent_id, lead_id, address, start_time_str, notes=None, db=None):
    return book_appointment(organization_id, agent_id, lead_id, start_time_str,
                             kind="site_visit", address=address, notes=notes, db=db)


def send_notification(organization_id, title, body, link=None, db=None):
    notification_service.notify(organization_id, title, body, ntype="general", link=link, db=db)
    return {"success": True}


def transfer_to_human(organization_id, conversation_id, reason="", db=None):
    db = db or get_db()
    db.conversations.update_one(
        {"_id": ObjectId(conversation_id), "organization_id": organization_id},
        {"$set": {"status": "handed_off", "updated_at": now()}},
    )
    notification_service.notify(
        organization_id,
        title="Human requested",
        body=reason or "A visitor asked to speak with a human",
        ntype="human_handoff",
        link=f"/dashboard/conversations/{conversation_id}",
        db=db,
    )
    return {"success": True}


TOOL_REGISTRY = {
    "search_knowledge": search_knowledge,
    "capture_lead": capture_lead,
    "update_lead": update_lead,
    "get_lead": get_lead,
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "request_site_visit": request_site_visit,
    "send_notification": send_notification,
    "transfer_to_human": transfer_to_human,
}