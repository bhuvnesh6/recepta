from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.extensions import get_db
from app.models import serialize, serialize_many, now
from app.security import login_required, get_scoped_organization_id

api_leads_bp = Blueprint("api_leads", __name__, url_prefix="/api/leads")


@api_leads_bp.get("")
@login_required
def list_leads():
    db = get_db()
    org_id = get_scoped_organization_id()
    q = {"organization_id": org_id}
    if request.args.get("status"):
        q["status"] = request.args.get("status")
    leads = list(db.leads.find(q).sort("created_at", -1).limit(500))
    return jsonify(serialize_many(leads))


@api_leads_bp.get("/<lead_id>")
@login_required
def get_lead_api(lead_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    lead = db.leads.find_one({"_id": ObjectId(lead_id), "organization_id": org_id})
    if not lead:
        return jsonify({"error": "not_found"}), 404
    return jsonify(serialize(lead))


@api_leads_bp.patch("/<lead_id>/status")
@login_required
def update_status(lead_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    status = data.get("status")
    valid = {"New", "Contacted", "Qualified", "Appointment", "Site Visit", "Won", "Lost"}
    if status not in valid:
        return jsonify({"error": "invalid_status"}), 400
    db.leads.update_one({"_id": ObjectId(lead_id), "organization_id": org_id},
                         {"$set": {"status": status, "updated_at": now()}})
    return jsonify({"status": status})


@api_leads_bp.post("/<lead_id>/assign")
@login_required
def assign_lead(lead_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    assignee = data.get("user_id")
    db.leads.update_one({"_id": ObjectId(lead_id), "organization_id": org_id},
                         {"$set": {"assigned_to": assignee, "updated_at": now()}})
    if assignee:
        from app.services.notification_service import notify
        lead = db.leads.find_one({"_id": ObjectId(lead_id)})
        notify(org_id, "Lead assigned to you", f"{lead.get('name') or 'A lead'} was assigned to you",
               ntype="lead_assigned", user_id=assignee, link=f"/dashboard/leads/{lead_id}")
    return jsonify({"assigned_to": assignee})


@api_leads_bp.post("/<lead_id>/notes")
@login_required
def add_note(lead_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    from app.security import current_user
    user = current_user()
    note = {"text": data.get("text", ""), "author": user["name"], "created_at": now()}
    db.leads.update_one({"_id": ObjectId(lead_id), "organization_id": org_id},
                         {"$push": {"notes": note}, "$set": {"updated_at": now()}})
    return jsonify(note)


# ---------------- Assignment rules ----------------

@api_leads_bp.get("/assignment-rules")
@login_required
def list_rules():
    db = get_db()
    org_id = get_scoped_organization_id()
    rules = list(db.assignment_rules.find({"organization_id": org_id}).sort("priority", 1))
    return jsonify(serialize_many(rules))


@api_leads_bp.post("/assignment-rules")
@login_required
def create_rule():
    from app.models import build_assignment_rule
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    rule = build_assignment_rule(org_id, data.get("name", "Rule"), data.get("conditions", []),
                                  data.get("assignee_user_id"), data.get("priority", 0))
    result = db.assignment_rules.insert_one(rule)
    rule["_id"] = result.inserted_id
    return jsonify(serialize(rule)), 201


@api_leads_bp.delete("/assignment-rules/<rule_id>")
@login_required
def delete_rule(rule_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.assignment_rules.delete_one({"_id": ObjectId(rule_id), "organization_id": org_id})
    return jsonify({"deleted": True})
