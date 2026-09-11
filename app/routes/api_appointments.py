from flask import Blueprint, request, jsonify
from bson import ObjectId
from datetime import datetime, timezone
from app.extensions import get_db
from app.models import serialize, serialize_many, now
from app.security import login_required, get_scoped_organization_id

api_appointments_bp = Blueprint("api_appointments", __name__, url_prefix="/api/appointments")


@api_appointments_bp.get("")
@login_required
def list_appointments():
    db = get_db()
    org_id = get_scoped_organization_id()
    appts = list(db.appointments.find({"organization_id": org_id}).sort("start_time", 1))
    return jsonify(serialize_many(appts))


@api_appointments_bp.patch("/<appointment_id>")
@login_required
def update_appointment(appointment_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    update = {"updated_at": now()}
    if data.get("status"):
        update["status"] = data["status"]
    if data.get("start_time"):
        start = datetime.strptime(data["start_time"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        update["start_time"] = start
        if data.get("status") != "canceled":
            update["status"] = "rescheduled"
    db.appointments.update_one({"_id": ObjectId(appointment_id), "organization_id": org_id}, {"$set": update})
    appt = db.appointments.find_one({"_id": ObjectId(appointment_id), "organization_id": org_id})
    return jsonify(serialize(appt))


@api_appointments_bp.post("/<appointment_id>/cancel")
@login_required
def cancel_appointment(appointment_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.appointments.update_one({"_id": ObjectId(appointment_id), "organization_id": org_id},
                                {"$set": {"status": "canceled", "updated_at": now()}})
    return jsonify({"status": "canceled"})
