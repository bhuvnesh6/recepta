"""
Recepta data model definitions.

MongoDB is schemaless, so these are plain builder/serializer helpers rather
than a heavyweight ORM. Every organization-owned collection carries
`organization_id` and must be queried with it (see app/security.py
get_scoped_organization_id, which is always derived server-side).
"""
from datetime import datetime, timezone
from bson import ObjectId


def now():
    return datetime.now(timezone.utc)


def oid_str(value):
    """Stringify ObjectId fields recursively for JSON responses."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [oid_str(v) for v in value]
    if isinstance(value, dict):
        return {k: oid_str(v) for k, v in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize(doc):
    if doc is None:
        return None
    return oid_str(doc)


def serialize_many(docs):
    return [serialize(d) for d in docs]


# ---------------- Builders ----------------

def build_user(email, password_hash, name, role, organization_id=None, team_role=None):
    return {
        "email": email.lower().strip(),
        "password_hash": password_hash,
        "name": name,
        "role": role,  # platform_admin | org_admin | team_user
        "team_role": team_role,  # e.g. "Sales", "Manager" (display only for team_user)
        "organization_id": organization_id,
        "is_active": True,
        "email_verified": False,
        "push_subscriptions": [],
        "notification_prefs": {"email": True, "browser_push": True},
        "created_at": now(),
        "updated_at": now(),
        "last_login_at": None,
    }


def build_plan(name, slug, monthly_price, setup_fee, features, limits):
    return {
        "name": name,
        "slug": slug,
        "monthly_price": monthly_price,
        "setup_fee": setup_fee,
        "features": features,   # list[str]
        "limits": limits,       # dict e.g. {"agents": 1, "voice_minutes": 500}
        "is_active": True,
        "created_at": now(),
        "updated_at": now(),
    }


def build_organization(name, industry="", website="", plan_slug="starter"):
    return {
        "name": name,
        "industry": industry,
        "website": website,
        "plan": plan_slug,
        "subscription_status": "trialing",  # trialing | active | past_due | suspended | canceled
        "subscription_start": None,
        "setup_payment_status": "pending",  # pending | paid
        "billing_customer_id": None,
        "billing_subscription_id": None,
        "status": "active",  # active | suspended
        "created_at": now(),
        "updated_at": now(),
    }


def build_agent(organization_id, name, business_name, industry="", description="", website=""):
    return {
        "organization_id": organization_id,
        "name": name,
        "business_name": business_name,
        "industry": industry,
        "description": description,
        "website": website,
        "status": "draft",  # draft | processing | ready | live | paused | archived
        "system_prompt": "",
        "personality": "",
        "language": "en",
        "greeting_text": f"Hi! Welcome to {business_name}. How can I help you today?",
        "greeting_audio_url": None,
        "voice": {"provider": "sarvam", "voice_id": "default"},
        "widget": {
            "primary_color": "#c8fa3d",
            "secondary_color": "#111318",
            "position": "bottom-right",
            "theme": "dark",
            "border_radius": 16,
            "avatar_url": None,
            "logo_url": None,
            "delay_seconds": 6,
        },
        "lead_fields": {
            "required": ["name", "email", "phone", "requirement"],
            "optional": ["location", "budget", "preferred_time"],
        },
        "tools_enabled": {
            "lead_capture": True,
            "booking": True,
            "site_visit": False,
            "human_handoff": True,
        },
        "test_mode_default": True,
        "created_at": now(),
        "updated_at": now(),
    }


def build_lead(organization_id, agent_id, name=None, email=None, phone=None,
                requirement=None, source="website_widget", conversation_id=None,
                location=None, budget=None, is_test=False):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
        "name": name,
        "email": email,
        "phone": phone,
        "requirement": requirement,
        "location": location,
        "budget": budget,
        "source": source,
        "status": "new",  # New Contacted Qualified Appointment Site Visit Won Lost
        "assigned_to": None,
        "qualification": "unqualified",
        "notes": [],
        "is_test": is_test,
        "created_at": now(),
        "updated_at": now(),
    }


def build_conversation(organization_id, agent_id, visitor_id, channel="chat", is_test=False):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "visitor_id": visitor_id,
        "channel": channel,  # chat | voice
        "status": "open",  # open | closed | handed_off
        "is_test": is_test,
        "visitor_ip": None,
        "lead_id": None,
        "created_at": now(),
        "updated_at": now(),
    }


def build_message(conversation_id, role, content, metadata=None):
    return {
        "conversation_id": conversation_id,
        "role": role,  # visitor | assistant | system | tool
        "content": content,
        "metadata": metadata or {},
        "created_at": now(),
    }


def build_appointment(organization_id, agent_id, lead_id, kind, start_time, end_time,
                       address=None, notes=None):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "lead_id": lead_id,
        "kind": kind,  # appointment | site_visit
        "status": "scheduled",  # scheduled | completed | canceled | rescheduled
        "start_time": start_time,
        "end_time": end_time,
        "address": address,
        "notes": notes,
        "created_at": now(),
        "updated_at": now(),
    }


def build_knowledge_source(organization_id, agent_id, source_type, source_url=None, file_name=None):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "source_type": source_type,  # website | pdf | docx | txt | csv
        "source_url": source_url,
        "file_name": file_name,
        "storage_path": None,
        "status": "processing",  # processing | ready | failed
        "pages_found": 0,
        "chunks_created": 0,
        "last_synced_at": None,
        "error": None,
        "created_at": now(),
        "updated_at": now(),
    }


def build_knowledge_chunk(organization_id, agent_id, source_id, content, embedding, metadata=None):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "source_id": source_id,
        "content": content,
        "embedding": embedding,
        "metadata": metadata or {},
        "created_at": now(),
    }


def build_notification(organization_id, user_id, ntype, title, body, link=None):
    return {
        "organization_id": organization_id,
        "user_id": user_id,  # None = broadcast to org admins
        "type": ntype,
        "title": title,
        "body": body,
        "link": link,
        "read": False,
        "created_at": now(),
    }


def build_usage_event(organization_id, agent_id, event_type, quantity):
    return {
        "organization_id": organization_id,
        "agent_id": agent_id,
        "type": event_type,  # ai_messages | voice_minutes | stt_seconds | tts_characters | embedding_ops | storage_mb
        "quantity": quantity,
        "created_at": now(),
    }


def build_assignment_rule(organization_id, name, conditions, assignee_user_id, priority=0):
    return {
        "organization_id": organization_id,
        "name": name,
        "conditions": conditions,  # list of {"field": "...", "op": "eq", "value": "..."}
        "assignee_user_id": assignee_user_id,
        "priority": priority,
        "is_active": True,
        "created_at": now(),
    }


def build_visitor(visitor_id, organization_id, ip_address=None, user_agent=None):
    return {
        "visitor_id": visitor_id,
        "organization_id": organization_id,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "first_seen_at": now(),
        "last_seen_at": now(),
        "visit_count": 1,
    }


def build_system_log(event_type, message, severity="info", organization_id=None,
                      agent_id=None, meta=None):
    return {
        "event_type": event_type,
        "message": message,
        "severity": severity,  # info | warning | error
        "organization_id": organization_id,
        "agent_id": agent_id,
        "meta": meta or {},
        "created_at": now(),
    }
