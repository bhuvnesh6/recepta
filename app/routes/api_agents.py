from flask import Blueprint, request, jsonify
from bson import ObjectId
from app.extensions import get_db
from app.models import build_agent, serialize, serialize_many, now
from app.security import login_required, roles_required, get_scoped_organization_id

api_agents_bp = Blueprint("api_agents", __name__, url_prefix="/api/agents")


@api_agents_bp.get("")
@login_required
def list_agents():
    db = get_db()
    org_id = get_scoped_organization_id()
    agents = list(db.agents.find({"organization_id": org_id}).sort("created_at", -1))
    return jsonify(serialize_many(agents))


@api_agents_bp.post("")
@roles_required("org_admin")
def create_agent():
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    agent = build_agent(
        org_id,
        name=data.get("name", "New Agent"),
        business_name=data.get("business_name", ""),
        industry=data.get("industry", ""),
        description=data.get("description", ""),
        website=data.get("website", ""),
    )
    result = db.agents.insert_one(agent)
    agent["_id"] = result.inserted_id
    return jsonify(serialize(agent)), 201


@api_agents_bp.get("/<agent_id>")
@login_required
def get_agent(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    if not agent:
        return jsonify({"error": "not_found"}), 404
    return jsonify(serialize(agent))


@api_agents_bp.patch("/<agent_id>")
@roles_required("org_admin")
def update_agent(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    data.pop("_id", None)
    data.pop("organization_id", None)
    data["updated_at"] = now()
    db.agents.update_one({"_id": ObjectId(agent_id), "organization_id": org_id}, {"$set": data})
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    return jsonify(serialize(agent))


@api_agents_bp.post("/<agent_id>/publish")
@roles_required("org_admin")
def publish_agent(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    if not agent:
        return jsonify({"error": "not_found"}), 404
    db.agents.update_one({"_id": ObjectId(agent_id)}, {"$set": {"status": "live", "updated_at": now()}})
    return jsonify({"status": "live", "embed_code":
                     f'<script src="{request.host_url.rstrip("/")}/widget.js" data-agent-id="{agent_id}"></script>'})


@api_agents_bp.post("/<agent_id>/pause")
@roles_required("org_admin")
def pause_agent(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.agents.update_one({"_id": ObjectId(agent_id), "organization_id": org_id},
                          {"$set": {"status": "paused", "updated_at": now()}})
    return jsonify({"status": "paused"})


@api_agents_bp.delete("/<agent_id>")
@roles_required("org_admin")
def delete_agent(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.agents.delete_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    db.knowledge_sources.delete_many({"agent_id": agent_id, "organization_id": org_id})
    db.knowledge_chunks.delete_many({"agent_id": agent_id, "organization_id": org_id})
    return jsonify({"deleted": True})


@api_agents_bp.post("/<agent_id>/test-chat")
@login_required
def test_chat(agent_id):
    """Live preview chat - always marked as a test conversation, never creates a real lead."""
    from app.services.chat_service import handle_visitor_message
    db = get_db()
    org_id = get_scoped_organization_id()
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    if not agent:
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(force=True)
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        from app.models import build_conversation
        conv = build_conversation(org_id, agent_id, "preview_" + agent_id, is_test=True)
        conv_result = db.conversations.insert_one(conv)
        conversation_id = str(conv_result.inserted_id)
    result = handle_visitor_message(org_id, agent, conversation_id, data.get("message", ""), is_test=True)
    result["conversation_id"] = conversation_id
    return jsonify(result)
