from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.extensions import get_db
from app.models import serialize_many
from app.security import login_required, get_scoped_organization_id, current_user

api_notifications_bp = Blueprint("api_notifications", __name__, url_prefix="/api/notifications")


@api_notifications_bp.get("")
@login_required
def list_notifications():
    db = get_db()
    org_id = get_scoped_organization_id()
    user = current_user()
    notes = list(db.notifications.find({
        "organization_id": org_id,
        "$or": [{"user_id": None}, {"user_id": str(user["_id"])}],
    }).sort("created_at", -1).limit(50))
    unread = db.notifications.count_documents({
        "organization_id": org_id,
        "$or": [{"user_id": None}, {"user_id": str(user["_id"])}],
        "read": False,
    })
    return jsonify({"notifications": serialize_many(notes), "unread_count": unread})


@api_notifications_bp.post("/<notification_id>/read")
@login_required
def mark_read(notification_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.notifications.update_one({"_id": ObjectId(notification_id), "organization_id": org_id},
                                 {"$set": {"read": True}})
    return jsonify({"read": True})


@api_notifications_bp.post("/push-subscribe")
@login_required
def push_subscribe():
    """Store a browser push subscription for the logged-in user."""
    db = get_db()
    user = current_user()
    subscription = request.get_json(force=True)
    db.users.update_one({"_id": user["_id"]}, {"$addToSet": {"push_subscriptions": subscription}})
    return jsonify({"subscribed": True})
