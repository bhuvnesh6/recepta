"""
Seed the database with:
  - a platform admin account
  - the three default plans (Starter / Growth / Pro)
  - an optional demo organization with an org admin, for quick testing

Run inside the container:
    docker compose exec web python migrations/seed.py

Or locally (with MONGO_URI pointed at your dev Mongo):
    python migrations/seed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import get_db
from app.models import build_user, build_plan, build_organization
from app.security import hash_password

ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@recepta.local")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe123!")
DEMO_ORG_NAME = os.environ.get("SEED_DEMO_ORG", "ABC Heating & Air")
DEMO_OWNER_EMAIL = os.environ.get("SEED_DEMO_OWNER_EMAIL", "owner@abcheating.local")
DEMO_OWNER_PASSWORD = os.environ.get("SEED_DEMO_OWNER_PASSWORD", "ChangeMe123!")


def run():
    app = create_app()
    with app.app_context():
        db = get_db()

        # ---- Platform admin ----
        if not db.users.find_one({"email": ADMIN_EMAIL}):
            db.users.insert_one(build_user(
                ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), "Platform Admin", role="platform_admin",
            ))
            print(f"Created platform admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        else:
            print(f"Platform admin already exists: {ADMIN_EMAIL}")

        # ---- Default plans ----
        default_plans = [
            ("Starter", "starter", 80, 249,
             ["1 AI agent", "1,000 AI messages/mo", "100 voice minutes/mo", "Website + PDF knowledge base",
              "Lead capture & notifications", "3 team members"],
             {"agents": 1, "voice_minutes": 100, "ai_messages": 1000, "team_members": 3}),
            ("Growth", "growth", 149, 249,
             ["2 AI agents", "5,000 AI messages/mo", "300 voice minutes/mo", "Appointment booking",
              "Automatic lead assignment", "10 team members"],
             {"agents": 2, "voice_minutes": 300, "ai_messages": 5000, "team_members": 10}),
            ("Pro", "pro", 199, 249,
             ["5 AI agents", "Unlimited AI messages", "800 voice minutes/mo", "Site visit scheduling",
              "Advanced analytics", "Unlimited team members"],
             {"agents": 5, "voice_minutes": 800, "ai_messages": -1, "team_members": -1}),
        ]
        for name, slug, price, setup_fee, features, limits in default_plans:
            if not db.plans.find_one({"slug": slug}):
                db.plans.insert_one(build_plan(name, slug, price, setup_fee, features, limits))
                print(f"Created plan: {name} (${price}/mo)")

        # ---- Demo organization ----
        if not db.users.find_one({"email": DEMO_OWNER_EMAIL}):
            org_doc = build_organization(DEMO_ORG_NAME, industry="HVAC", plan_slug="growth")
            org_doc["subscription_status"] = "active"
            org_result = db.organizations.insert_one(org_doc)
            org_id = str(org_result.inserted_id)
            db.users.insert_one(build_user(
                DEMO_OWNER_EMAIL, hash_password(DEMO_OWNER_PASSWORD), "Demo Owner",
                role="org_admin", organization_id=org_id,
            ))
            print(f"Created demo organization '{DEMO_ORG_NAME}' with owner: {DEMO_OWNER_EMAIL} / {DEMO_OWNER_PASSWORD}")
        else:
            print(f"Demo organization owner already exists: {DEMO_OWNER_EMAIL}")

        print("\nSeed complete.")


if __name__ == "__main__":
    run()
