from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.extensions import get_db
from app.models import serialize, serialize_many
from app.security import login_required, get_scoped_organization_id

api_conversations_bp = Blueprint("api_conversations", __name__, url_prefix="/api/conversations")


@api_conversations_bp.get("")
@login_required
def list_conversations():
    db = get_db()
    org_id = get_scoped_organization_id()
    q = {"organization_id": org_id}
    if request.args.get("channel"):
        q["channel"] = request.args.get("channel")
    convs = list(db.conversations.find(q).sort("updated_at", -1).limit(200))
    agent_map = {str(a["_id"]): a["name"] for a in db.agents.find({"organization_id": org_id})}
    for c in convs:
        c["agent_name"] = agent_map.get(c.get("agent_id"), "Agent")
        last_msg = db.messages.find_one({"conversation_id": str(c["_id"])}, sort=[("created_at", -1)])
        c["preview"] = last_msg["content"][:80] if last_msg else ""
    return jsonify(serialize_many(convs))


@api_conversations_bp.get("/<conversation_id>")
@login_required
def get_conversation(conversation_id):
    """Returns the full transcript - chat or voice (voice messages carry a
    transcript in `content`, plus optional `metadata.audio_url`)."""
    db = get_db()
    org_id = get_scoped_organization_id()
    conv = db.conversations.find_one({"_id": ObjectId(conversation_id), "organization_id": org_id})
    if not conv:
        return jsonify({"error": "not_found"}), 404
    messages = list(db.messages.find({"conversation_id": conversation_id}).sort("created_at", 1))
    return jsonify({"conversation": serialize(conv), "messages": serialize_many(messages)})


@api_conversations_bp.post("/<conversation_id>/handoff")
@login_required
def handoff(conversation_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.conversations.update_one({"_id": ObjectId(conversation_id), "organization_id": org_id},
                                 {"$set": {"status": "handed_off"}})
    return jsonify({"status": "handed_off"})


@api_conversations_bp.post("/<conversation_id>/close")
@login_required
def close_conversation(conversation_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.conversations.update_one({"_id": ObjectId(conversation_id), "organization_id": org_id},
                                 {"$set": {"status": "closed"}})
    return jsonify({"status": "closed"})
