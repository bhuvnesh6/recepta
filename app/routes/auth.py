import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.extensions import get_db
from app.models import build_user, build_organization, now
from app.security import (
    hash_password, verify_password, login_user, logout_user, current_user,
    login_required, rate_limited,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login():
    if current_user():
        return redirect(url_for("dashboard.index"))
    return render_template("auth/login.html")


@auth_bp.post("/login")
def login_post():
    db = get_db()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if rate_limited(f"login:{email}:{request.remote_addr}", max_attempts=8, window_seconds=300):
        flash("Too many attempts. Please wait a few minutes and try again.", "error")
        return redirect(url_for("auth.login"))

    user = db.users.find_one({"email": email, "is_active": True})
    if not user or not verify_password(password, user["password_hash"]):
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.login"))

    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now()}})
    login_user(user)

    if user["role"] == "platform_admin":
        return redirect(url_for("admin.index"))
    return redirect(url_for("dashboard.index"))


@auth_bp.get("/register")
def register():
    if current_user():
        return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html")


@auth_bp.post("/register")
def register_post():
    db = get_db()
    org_name = request.form.get("org_name", "").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not (org_name and name and email and len(password) >= 8):
        flash("Please fill all fields. Password must be at least 8 characters.", "error")
        return redirect(url_for("auth.register"))

    if db.users.find_one({"email": email}):
        flash("An account with that email already exists.", "error")
        return redirect(url_for("auth.register"))

    org_doc = build_organization(org_name, plan_slug="starter")
    org_result = db.organizations.insert_one(org_doc)
    organization_id = str(org_result.inserted_id)

    user_doc = build_user(email, hash_password(password), name, role="org_admin",
                           organization_id=organization_id)
    user_result = db.users.insert_one(user_doc)
    user_doc["_id"] = user_result.inserted_id

    login_user(user_doc)
    flash("Welcome to Recepta! Let's create your first AI receptionist.", "success")
    return redirect(url_for("dashboard.agents"))


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.get("/api/auth/me")
@login_required
def me():
    from app.models import serialize
    user = current_user()
    user = dict(user)
    user.pop("password_hash", None)
    return jsonify(serialize(user))


@auth_bp.get("/forgot-password")
def forgot_password():
    return render_template("auth/forgot_password.html")


@auth_bp.post("/forgot-password")
def forgot_password_post():
    # MVP stub: in production, email a signed reset token via the email provider.
    flash("If that email exists in our system, a reset link has been sent.", "success")
    return redirect(url_for("auth.login"))
