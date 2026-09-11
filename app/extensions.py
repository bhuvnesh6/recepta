from pymongo import MongoClient
from flask import current_app, g


def get_db():
    """Return the MongoDB database handle for the current app context."""
    if "db" not in g:
        client = MongoClient(current_app.config["MONGO_URI"])
        g.mongo_client = client
        g.db = client[current_app.config["MONGO_DB_NAME"]]
    return g.db


def close_db(e=None):
    client = g.pop("mongo_client", None)
    if client is not None:
        client.close()


def init_indexes(db):
    """Create indexes required for multi-tenant scoping and lookups."""
    db.users.create_index("email", unique=True)
    db.users.create_index("organization_id")

    db.organizations.create_index("name")
    db.organizations.create_index("subscription_status")

    db.agents.create_index("organization_id")
    db.agents.create_index([("organization_id", 1), ("status", 1)])

    db.leads.create_index("organization_id")
    db.leads.create_index([("organization_id", 1), ("status", 1)])
    db.leads.create_index("email")
    db.leads.create_index("phone")
    db.leads.create_index("created_at")

    db.conversations.create_index("organization_id")
    db.conversations.create_index("agent_id")
    db.conversations.create_index("visitor_id")
    db.conversations.create_index("created_at")

    db.messages.create_index("conversation_id")
    db.messages.create_index("created_at")

    db.appointments.create_index("organization_id")
    db.appointments.create_index("agent_id")
    db.appointments.create_index("start_time")

    db.knowledge_sources.create_index("organization_id")
    db.knowledge_sources.create_index("agent_id")

    db.knowledge_chunks.create_index([("organization_id", 1), ("agent_id", 1)])

    db.notifications.create_index("organization_id")
    db.notifications.create_index("user_id")
    db.notifications.create_index("created_at")

    db.usage_events.create_index([("organization_id", 1), ("type", 1)])
    db.usage_events.create_index("created_at")

    db.plans.create_index("slug", unique=True)

    db.visitors.create_index("visitor_id", unique=True)
    db.visitors.create_index("organization_id")

    db.system_logs.create_index("created_at")
    db.system_logs.create_index("event_type")
