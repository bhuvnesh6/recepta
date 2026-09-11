"""
Notification service. Creates in-app notification records and fans out to
browser push (via stored subscriptions) and email. SMS/Slack/Teams can be
added later as additional channels without changing callers - they all
just call notify(...).
"""
from app.extensions import get_db
from app.models import build_notification


def notify(organization_id, title, body, ntype="general", user_id=None, link=None):
    db = get_db()
    doc = build_notification(organization_id, user_id, ntype, title, body, link)
    result = db.notifications.insert_one(doc)
    doc["_id"] = result.inserted_id
    _dispatch_browser_push(doc)
    _dispatch_email(doc)
    return doc


def _dispatch_browser_push(notification):
    """Push to stored subscriptions for the target user(s). Requires VAPID
    keys + a push library (e.g. pywebpush) to be wired in production; this
    stub keeps the interface stable so the frontend/service worker can be
    built against it today."""
    pass


def _dispatch_email(notification):
    """Send via SMTP/provider of choice. Stub keeps the call site stable."""
    pass


def notify_new_lead(organization_id, lead, assignee_user_id=None):
    notify(
        organization_id,
        title="New lead from website",
        body=f"{lead.get('name') or 'A visitor'} - {lead.get('requirement') or 'New inquiry'}",
        ntype="new_lead",
        link=f"/dashboard/leads/{lead['_id']}",
    )
    if assignee_user_id:
        notify(
            organization_id,
            title="Lead assigned to you",
            body=f"{lead.get('name') or 'A new lead'} was assigned to you",
            ntype="lead_assigned",
            user_id=assignee_user_id,
            link=f"/dashboard/leads/{lead['_id']}",
        )


def notify_appointment_booked(organization_id, appointment):
    notify(
        organization_id,
        title="New appointment booked",
        body=f"{appointment.get('kind', 'appointment').replace('_', ' ').title()} scheduled",
        ntype="appointment_booked",
        link=f"/dashboard/appointments",
    )
