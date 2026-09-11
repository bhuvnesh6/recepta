from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from bson import ObjectId
from datetime import datetime, timedelta, timezone

from app.extensions import get_db
from app.models import build_user, build_organization, build_plan, serialize, serialize_many, now
from app.security import hash_password, roles_required, current_user

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/")
@roles_required("platform_admin")
def index():
    db = get_db()
    since_30d = now() - timedelta(days=30)

    stats = {
        "total_orgs": db.organizations.count_documents({}),
        "active_orgs": db.organizations.count_documents({"status": "active"}),
        "total_agents": db.agents.count_documents({}),
        "active_agents": db.agents.count_documents({"status": "live"}),
        "total_leads": db.leads.count_documents({}),
        "total_conversations": db.conversations.count_documents({}),
        "total_appointments": db.appointments.count_documents({}),
        "recent_signups": db.organizations.count_documents({"created_at": {"$gte": since_30d}}),
    }

    usage_agg = list(db.usage_events.aggregate([
        {"$match": {"created_at": {"$gte": since_30d}}},
        {"$group": {"_id": "$type", "total": {"$sum": "$quantity"}}},
    ]))
    usage = {r["_id"]: r["total"] for r in usage_agg}

    recent_orgs = list(db.organizations.find().sort("created_at", -1).limit(8))
    return render_template("admin/dashboard.html", stats=stats, usage=usage,
                            recent_orgs=serialize_many(recent_orgs))


@admin_bp.get("/organizations")
@roles_required("platform_admin")
def organizations():
    db = get_db()
    orgs = list(db.organizations.find().sort("created_at", -1))
    for o in orgs:
        o["agent_count"] = db.agents.count_documents({"organization_id": str(o["_id"])})
        o["user_count"] = db.users.count_documents({"organization_id": str(o["_id"])})
    plans = list(db.plans.find({"is_active": True}))
    return render_template("admin/organizations.html", orgs=serialize_many(orgs), plans=serialize_many(plans))


@admin_bp.post("/organizations")
@roles_required("platform_admin")
def create_organization():
    db = get_db()
    name = request.form.get("name", "").strip()
    plan_slug = request.form.get("plan", "starter")
    owner_email = request.form.get("owner_email", "").strip().lower()
    owner_name = request.form.get("owner_name", "").strip()
    owner_password = request.form.get("owner_password", "") or "changeme123"

    if not name:
        flash("Organization name is required.", "error")
        return redirect(url_for("admin.organizations"))

    org_doc = build_organization(name, plan_slug=plan_slug)
    org_doc["subscription_status"] = "active"
    result = db.organizations.insert_one(org_doc)
    org_id = str(result.inserted_id)

    if owner_email:
        if not db.users.find_one({"email": owner_email}):
            user_doc = build_user(owner_email, hash_password(owner_password), owner_name or name,
                                   role="org_admin", organization_id=org_id)
            db.users.insert_one(user_doc)

    flash(f"Organization '{name}' created.", "success")
    return redirect(url_for("admin.organizations"))


@admin_bp.post("/organizations/<org_id>/suspend")
@roles_required("platform_admin")
def suspend_organization(org_id):
    db = get_db()
    db.organizations.update_one({"_id": ObjectId(org_id)}, {"$set": {"status": "suspended", "updated_at": now()}})
    return redirect(url_for("admin.organizations"))


@admin_bp.post("/organizations/<org_id>/activate")
@roles_required("platform_admin")
def activate_organization(org_id):
    db = get_db()
    db.organizations.update_one({"_id": ObjectId(org_id)}, {"$set": {"status": "active", "updated_at": now()}})
    return redirect(url_for("admin.organizations"))


@admin_bp.post("/organizations/<org_id>/delete")
@roles_required("platform_admin")
def delete_organization(org_id):
    db = get_db()
    db.organizations.delete_one({"_id": ObjectId(org_id)})
    db.users.delete_many({"organization_id": org_id})
    db.agents.delete_many({"organization_id": org_id})
    flash("Organization and its data removed.", "success")
    return redirect(url_for("admin.organizations"))


@admin_bp.get("/organizations/<org_id>")
@roles_required("platform_admin")
def organization_detail(org_id):
    db = get_db()
    org = db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org:
        flash("Organization not found.", "error")
        return redirect(url_for("admin.organizations"))
    agents = list(db.agents.find({"organization_id": org_id}))
    users = list(db.users.find({"organization_id": org_id}))
    leads_count = db.leads.count_documents({"organization_id": org_id})
    return render_template("admin/organization_detail.html", org=serialize(org),
                            agents=serialize_many(agents), users=serialize_many(users),
                            leads_count=leads_count)


@admin_bp.post("/organizations/<org_id>/impersonate")
@roles_required("platform_admin")
def impersonate(org_id):
    """Controlled read/support view of an org's dashboard without exposing credentials."""
    db = get_db()
    org_admin = db.users.find_one({"organization_id": org_id, "role": "org_admin"})
    if not org_admin:
        flash("This organization has no admin user to view as.", "error")
        return redirect(url_for("admin.organizations"))
    session["impersonating_admin_id"] = session.get("user_id")
    session["user_id"] = str(org_admin["_id"])
    session["role"] = org_admin["role"]
    session["organization_id"] = org_id
    flash(f"Viewing as {org_admin['name']} (support mode).", "success")
    return redirect(url_for("dashboard.index"))


@admin_bp.post("/stop-impersonating")
def stop_impersonating():
    admin_id = session.get("impersonating_admin_id")
    if admin_id:
        db = get_db()
        admin_user = db.users.find_one({"_id": ObjectId(admin_id)})
        if admin_user:
            session["user_id"] = str(admin_user["_id"])
            session["role"] = admin_user["role"]
            session["organization_id"] = None
        session.pop("impersonating_admin_id", None)
    return redirect(url_for("admin.index"))


@admin_bp.get("/users")
@roles_required("platform_admin")
def users():
    db = get_db()
    all_users = list(db.users.find().sort("created_at", -1))
    org_map = {str(o["_id"]): o["name"] for o in db.organizations.find()}
    for u in all_users:
        u.pop("password_hash", None)
        u["org_name"] = org_map.get(u.get("organization_id"), "-")
    return render_template("admin/users.html", users=serialize_many(all_users))


@admin_bp.post("/users/<user_id>/deactivate")
@roles_required("platform_admin")
def deactivate_user(user_id):
    db = get_db()
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": False}})
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<user_id>/activate")
@roles_required("platform_admin")
def activate_user(user_id):
    db = get_db()
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_active": True}})
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<user_id>/delete")
@roles_required("platform_admin")
def delete_user(user_id):
    db = get_db()
    db.users.delete_one({"_id": ObjectId(user_id)})
    flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


# ---------------- Plans ----------------

@admin_bp.get("/plans")
@roles_required("platform_admin")
def plans():
    db = get_db()
    all_plans = list(db.plans.find().sort("monthly_price", 1))
    return render_template("admin/plans.html", plans=serialize_many(all_plans))


@admin_bp.post("/plans")
@roles_required("platform_admin")
def create_plan():
    db = get_db()
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip().lower().replace(" ", "-")
    monthly_price = float(request.form.get("monthly_price", 0) or 0)
    setup_fee = float(request.form.get("setup_fee", 249) or 0)
    features = [f.strip() for f in request.form.get("features", "").split("\n") if f.strip()]
    limits = {
        "agents": int(request.form.get("limit_agents", 1) or 1),
        "voice_minutes": int(request.form.get("limit_voice_minutes", 100) or 100),
        "ai_messages": int(request.form.get("limit_ai_messages", 1000) or 1000),
        "team_members": int(request.form.get("limit_team_members", 3) or 3),
    }
    if not (name and slug):
        flash("Plan name and slug are required.", "error")
        return redirect(url_for("admin.plans"))
    if db.plans.find_one({"slug": slug}):
        flash("A plan with that slug already exists.", "error")
        return redirect(url_for("admin.plans"))
    db.plans.insert_one(build_plan(name, slug, monthly_price, setup_fee, features, limits))
    flash(f"Plan '{name}' created.", "success")
    return redirect(url_for("admin.plans"))


@admin_bp.post("/plans/<plan_id>/update")
@roles_required("platform_admin")
def update_plan(plan_id):
    db = get_db()
    features = [f.strip() for f in request.form.get("features", "").split("\n") if f.strip()]
    db.plans.update_one({"_id": ObjectId(plan_id)}, {"$set": {
        "name": request.form.get("name", "").strip(),
        "monthly_price": float(request.form.get("monthly_price", 0) or 0),
        "setup_fee": float(request.form.get("setup_fee", 0) or 0),
        "features": features,
        "updated_at": now(),
    }})
    flash("Plan updated.", "success")
    return redirect(url_for("admin.plans"))


@admin_bp.post("/plans/<plan_id>/delete")
@roles_required("platform_admin")
def delete_plan(plan_id):
    db = get_db()
    db.plans.delete_one({"_id": ObjectId(plan_id)})
    return redirect(url_for("admin.plans"))


@admin_bp.get("/logs")
@roles_required("platform_admin")
def logs():
    db = get_db()
    q = {}
    if request.args.get("event_type"):
        q["event_type"] = request.args.get("event_type")
    if request.args.get("severity"):
        q["severity"] = request.args.get("severity")
    if request.args.get("organization_id"):
        q["organization_id"] = request.args.get("organization_id")
    entries = list(db.system_logs.find(q).sort("created_at", -1).limit(200))
    return render_template("admin/logs.html", logs=serialize_many(entries))
