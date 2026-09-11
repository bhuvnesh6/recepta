from app.extensions import get_db
from app.models import build_usage_event


def track(organization_id, agent_id, event_type, quantity=1):
    db = get_db()
    db.usage_events.insert_one(build_usage_event(organization_id, agent_id, event_type, quantity))


def summary(organization_id, since=None):
    db = get_db()
    match = {"organization_id": organization_id}
    if since:
        match["created_at"] = {"$gte": since}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$type", "total": {"$sum": "$quantity"}}},
    ]
    rows = list(db.usage_events.aggregate(pipeline))
    return {r["_id"]: r["total"] for r in rows}
