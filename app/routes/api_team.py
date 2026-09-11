from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.extensions import get_db
from app.models import serialize_many, now
from app.security import login_required, roles_required, get_scoped_organization_id, hash_password, current_user

api_team_bp = Blueprint("api_team", __name__, url_prefix="/api/team")


@api_team_bp.get("")
@login_required
def list_team():
    db = get_db()
    org_id = get_scoped_organization_id()
    members = list(db.users.find({"organization_id": org_id, "role": {"$in": ["org_admin", "team_user"]}}))
    for m in members:
        m.pop("password_hash", None)
    return jsonify(serialize_many(members))


@api_team_bp.patch("/<user_id>")
@roles_required("org_admin")
def update_member(user_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    allowed = {"name", "team_role", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = now()
    db.users.update_one({"_id": ObjectId(user_id), "organization_id": org_id, "role": "team_user"},
                         {"$set": update})
    return jsonify({"updated": True})


@api_team_bp.patch("/me/password")
@login_required
def change_my_password():
    db = get_db()
    user = current_user()
    data = request.get_json(force=True)
    new_password = data.get("new_password", "")
    if len(new_password) < 8:
        return jsonify({"error": "password_too_short"}), 400
    db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(new_password)}})
    return jsonify({"updated": True})
