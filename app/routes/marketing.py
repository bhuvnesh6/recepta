"""
Public marketing site: landing page + legal pages. Anyone already logged in
who lands on "/" (or clicks Login/Sign up) is sent straight to their
dashboard - the marketing site is only ever shown to signed-out visitors.
"""
from flask import Blueprint, render_template, redirect, url_for
from app.security import current_user

marketing_bp = Blueprint("marketing", __name__)


@marketing_bp.get("/")
def landing():
    user = current_user()
    if user:
        if user["role"] == "platform_admin":
            return redirect(url_for("admin.index"))
        return redirect(url_for("dashboard.index"))
    return render_template("marketing/landing.html")


_LEGAL_PAGES = {
    "privacy-policy": "Privacy Policy",
    "terms": "Terms & Conditions",
    "disclaimer": "Disclaimer",
}


@marketing_bp.get("/privacy-policy")
def privacy_policy():
    return render_template("marketing/legal.html", title="Privacy Policy", section="privacy")


@marketing_bp.get("/terms")
def terms():
    return render_template("marketing/legal.html", title="Terms & Conditions", section="terms")


@marketing_bp.get("/disclaimer")
def disclaimer():
    return render_template("marketing/legal.html", title="Disclaimer", section="disclaimer")