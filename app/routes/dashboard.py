from datetime import timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from bson import ObjectId

from app.extensions import get_db
from app.models import serialize, serialize_many, now
from app.security import login_required, roles_required, current_user, get_scoped_organization_id
from app.services import usage_service

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.get("")
@login_required
def index():
    db = get_db()
    org_id = get_scoped_organization_id()
    since_30d = now() - timedelta(days=30)
    since_60d = now() - timedelta(days=60)

    def counts_between(collection, extra=None, start=None, end=None):
        q = {"organization_id": org_id}
        if extra:
            q.update(extra)
        if start or end:
            date_q = {}
            if start:
                date_q["$gte"] = start
            if end:
                date_q["$lt"] = end
            q["created_at"] = date_q
        return db[collection].count_documents(q)

    stats = {
        "total_visitors": db.visitors.count_documents({"organization_id": org_id, "first_seen_at": {"$gte": since_30d}}),
        "conversations": counts_between("conversations", start=since_30d),
        "qualified_leads": counts_between("leads", {"qualification": "qualified"}, start=since_30d),
        "appointments": counts_between("appointments", start=since_30d),
    }
    total_leads_30d = counts_between("leads", start=since_30d)
    stats["conversion_rate"] = round((total_leads_30d / stats["total_visitors"] * 100), 1) if stats["total_visitors"] else 0.0

    prev = {
        "total_visitors": db.visitors.count_documents({"organization_id": org_id, "first_seen_at": {"$gte": since_60d, "$lt": since_30d}}),
        "conversations": counts_between("conversations", start=since_60d, end=since_30d),
        "qualified_leads": counts_between("leads", {"qualification": "qualified"}, start=since_60d, end=since_30d),
        "appointments": counts_between("appointments", start=since_60d, end=since_30d),
    }

    def pct_change(cur, prev_v):
        if not prev_v:
            return 100.0 if cur else 0.0
        return round((cur - prev_v) / prev_v * 100, 1)

    deltas = {k: pct_change(stats[k], prev[k]) for k in ["total_visitors", "conversations", "qualified_leads", "appointments"]}

    recent_leads = list(db.leads.find({"organization_id": org_id}).sort("created_at", -1).limit(5))
    recent_conversations = list(db.conversations.find({"organization_id": org_id}).sort("updated_at", -1).limit(6))
    for c in recent_conversations:
        last_msg = db.messages.find_one({"conversation_id": str(c["_id"])}, sort=[("created_at", -1)])
        c["last_message"] = last_msg["content"][:60] if last_msg else ""
        agent = db.agents.find_one({"_id": ObjectId(c["agent_id"])}) if c.get("agent_id") else None
        c["agent_name"] = agent["name"] if agent else "Agent"

    team = list(db.users.find({"organization_id": org_id, "role": {"$in": ["org_admin", "team_user"]}}))
    for m in team:
        m["lead_count"] = db.leads.count_documents({"organization_id": org_id, "assigned_to": str(m["_id"])})
        m["appt_count"] = db.appointments.count_documents({"organization_id": org_id, "lead_id": {"$in": [
            str(l["_id"]) for l in db.leads.find({"organization_id": org_id, "assigned_to": str(m["_id"])}, {"_id": 1})
        ]}})

    lead_sources = list(db.leads.aggregate([
        {"$match": {"organization_id": org_id}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]))

    org = db.organizations.find_one({"_id": ObjectId(org_id)})

    return render_template(
        "dashboard/index.html", stats=stats, deltas=deltas,
        recent_leads=serialize_many(recent_leads),
        recent_conversations=serialize_many(recent_conversations),
        team=serialize_many(team), lead_sources=lead_sources,
        org=serialize(org),
    )


@dashboard_bp.get("/agents")
@login_required
def agents():
    db = get_db()
    org_id = get_scoped_organization_id()
    agent_list = list(db.agents.find({"organization_id": org_id}).sort("created_at", -1))
    return render_template("dashboard/agents.html", agents=serialize_many(agent_list))


@dashboard_bp.get("/agents/new")
@roles_required("org_admin")
def agent_new():
    return render_template("dashboard/agent_wizard.html", agent=None)


@dashboard_bp.get("/agents/<agent_id>")
@login_required
def agent_detail(agent_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id})
    if not agent:
        flash("Agent not found.", "error")
        return redirect(url_for("dashboard.agents"))
    sources = list(db.knowledge_sources.find({"agent_id": agent_id}))
    widget_snippet = f'<script src="{request.host_url.rstrip("/")}/widget.js" data-agent-id="{agent_id}"></script>'
    return render_template("dashboard/agent_detail.html", agent=serialize(agent),
                            sources=serialize_many(sources), widget_snippet=widget_snippet)


@dashboard_bp.get("/leads")
@login_required
def leads():
    db = get_db()
    org_id = get_scoped_organization_id()
    status = request.args.get("status")
    q = {"organization_id": org_id}
    if status:
        q["status"] = status
    lead_list = list(db.leads.find(q).sort("created_at", -1).limit(200))
    user_map = {str(u["_id"]): u["name"] for u in db.users.find({"organization_id": org_id})}
    for l in lead_list:
        l["assignee_name"] = user_map.get(l.get("assigned_to"), "Unassigned")
    team = list(db.users.find({"organization_id": org_id, "role": {"$in": ["org_admin", "team_user"]}}))
    return render_template("dashboard/leads.html", leads=serialize_many(lead_list),
                            team=serialize_many(team), status_filter=status or "")


@dashboard_bp.get("/leads/<lead_id>")
@login_required
def lead_detail(lead_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    lead = db.leads.find_one({"_id": ObjectId(lead_id), "organization_id": org_id})
    if not lead:
        flash("Lead not found.", "error")
        return redirect(url_for("dashboard.leads"))
    conversation = None
    messages = []
    if lead.get("conversation_id"):
        conversation = db.conversations.find_one({"_id": ObjectId(lead["conversation_id"])})
        messages = list(db.messages.find({"conversation_id": lead["conversation_id"]}).sort("created_at", 1))
    appointments = list(db.appointments.find({"lead_id": lead_id}))
    team = list(db.users.find({"organization_id": org_id, "role": {"$in": ["org_admin", "team_user"]}}))
    return render_template("dashboard/lead_detail.html", lead=serialize(lead),
                            conversation=serialize(conversation), messages=serialize_many(messages),
                            appointments=serialize_many(appointments), team=serialize_many(team))


@dashboard_bp.get("/conversations")
@login_required
def conversations():
    db = get_db()
    org_id = get_scoped_organization_id()
    conv_list = list(db.conversations.find({"organization_id": org_id}).sort("updated_at", -1).limit(100))
    agent_map = {str(a["_id"]): a["name"] for a in db.agents.find({"organization_id": org_id})}
    for c in conv_list:
        c["agent_name"] = agent_map.get(c.get("agent_id"), "Agent")
        last_msg = db.messages.find_one({"conversation_id": str(c["_id"])}, sort=[("created_at", -1)])
        c["preview"] = (last_msg["content"][:70] if last_msg else "")
        c["message_count"] = db.messages.count_documents({"conversation_id": str(c["_id"])})
    selected_id = request.args.get("id") or (conv_list[0]["_id"] if conv_list else None)
    selected = None
    messages = []
    if selected_id:
        selected = db.conversations.find_one({"_id": ObjectId(str(selected_id)), "organization_id": org_id})
        if selected:
            messages = list(db.messages.find({"conversation_id": str(selected["_id"])}).sort("created_at", 1))
            selected["agent_name"] = agent_map.get(selected.get("agent_id"), "Agent")
    return render_template("dashboard/conversations.html", conversations=serialize_many(conv_list),
                            selected=serialize(selected), messages=serialize_many(messages))


@dashboard_bp.get("/appointments")
@login_required
def appointments():
    db = get_db()
    org_id = get_scoped_organization_id()
    appt_list = list(db.appointments.find({"organization_id": org_id}).sort("start_time", 1))
    lead_map = {str(l["_id"]): l for l in db.leads.find({"organization_id": org_id})}
    for a in appt_list:
        lead = lead_map.get(a.get("lead_id"), {})
        a["lead_name"] = lead.get("name", "Unknown")
        a["lead_phone"] = lead.get("phone", "")
    return render_template("dashboard/appointments.html", appointments=serialize_many(appt_list))


@dashboard_bp.get("/knowledge")
@login_required
def knowledge():
    db = get_db()
    org_id = get_scoped_organization_id()
    agent_list = list(db.agents.find({"organization_id": org_id}))
    agent_id = request.args.get("agent_id") or (str(agent_list[0]["_id"]) if agent_list else None)
    sources = []
    if agent_id:
        sources = list(db.knowledge_sources.find({"organization_id": org_id, "agent_id": agent_id}).sort("created_at", -1))
    return render_template("dashboard/knowledge.html", agents=serialize_many(agent_list),
                            sources=serialize_many(sources), selected_agent_id=agent_id)


@dashboard_bp.get("/team")
@roles_required("org_admin")
def team():
    db = get_db()
    org_id = get_scoped_organization_id()
    members = list(db.users.find({"organization_id": org_id, "role": {"$in": ["org_admin", "team_user"]}}))
    return render_template("dashboard/team.html", team=serialize_many(members))


@dashboard_bp.post("/team")
@roles_required("org_admin")
def team_create():
    from app.models import build_user
    from app.security import hash_password
    db = get_db()
    org_id = get_scoped_organization_id()
    email = request.form.get("email", "").strip().lower()
    name = request.form.get("name", "").strip()
    team_role = request.form.get("team_role", "Sales")
    password = request.form.get("password") or "changeme123"
    if db.users.find_one({"email": email}):
        flash("A user with that email already exists.", "error")
        return redirect(url_for("dashboard.team"))
    db.users.insert_one(build_user(email, hash_password(password), name, role="team_user",
                                    organization_id=org_id, team_role=team_role))
    flash(f"{name} added to the team.", "success")
    return redirect(url_for("dashboard.team"))


@dashboard_bp.post("/team/<user_id>/remove")
@roles_required("org_admin")
def team_remove(user_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    db.users.delete_one({"_id": ObjectId(user_id), "organization_id": org_id, "role": "team_user"})
    return redirect(url_for("dashboard.team"))


@dashboard_bp.get("/notifications")
@login_required
def notifications():
    db = get_db()
    org_id = get_scoped_organization_id()
    user = current_user()
    notes = list(db.notifications.find({
        "organization_id": org_id,
        "$or": [{"user_id": None}, {"user_id": str(user["_id"])}],
    }).sort("created_at", -1).limit(100))
    db.notifications.update_many(
        {"organization_id": org_id, "$or": [{"user_id": None}, {"user_id": str(user["_id"])}]},
        {"$set": {"read": True}},
    )
    return render_template("dashboard/notifications.html", notifications=serialize_many(notes))


@dashboard_bp.get("/analytics")
@login_required
def analytics():
    db = get_db()
    org_id = get_scoped_organization_id()
    return render_template("dashboard/analytics.html")


@dashboard_bp.get("/usage")
@login_required
def usage():
    org_id = get_scoped_organization_id()
    data = usage_service.summary(org_id)
    return render_template("dashboard/usage.html", usage=data)


@dashboard_bp.get("/settings")
@roles_required("org_admin")
def settings():
    db = get_db()
    org_id = get_scoped_organization_id()
    org = db.organizations.find_one({"_id": ObjectId(org_id)})
    return render_template("dashboard/settings.html", org=serialize(org))


@dashboard_bp.post("/settings")
@roles_required("org_admin")
def settings_update():
    db = get_db()
    org_id = get_scoped_organization_id()
    db.organizations.update_one({"_id": ObjectId(org_id)}, {"$set": {
        "name": request.form.get("name", "").strip(),
        "industry": request.form.get("industry", "").strip(),
        "website": request.form.get("website", "").strip(),
        "updated_at": now(),
    }})
    flash("Settings saved.", "success")
    return redirect(url_for("dashboard.settings"))


@dashboard_bp.get("/billing")
@roles_required("org_admin")
def billing():
    db = get_db()
    org_id = get_scoped_organization_id()
    org = db.organizations.find_one({"_id": ObjectId(org_id)})
    plan = db.plans.find_one({"slug": org.get("plan")}) if org else None
    return render_template("dashboard/billing.html", org=serialize(org), plan=serialize(plan))
