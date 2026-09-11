"""
Lead assignment engine: evaluates active rules in priority order, falls
back to round robin among the org's online team members.
"""
from app.extensions import get_db

OPS = {
    "eq": lambda a, b: str(a).lower() == str(b).lower(),
    "contains": lambda a, b: str(b).lower() in str(a or "").lower(),
    "gt": lambda a, b: (a or 0) > b,
    "gte": lambda a, b: (a or 0) >= b,
}


def _rule_matches(lead, rule):
    for cond in rule.get("conditions", []):
        field, op, value = cond.get("field"), cond.get("op", "eq"), cond.get("value")
        lead_value = lead.get(field)
        fn = OPS.get(op, OPS["eq"])
        try:
            if not fn(lead_value, value):
                return False
        except Exception:
            return False
    return True


def _round_robin_assignee(organization_id):
    db = get_db()
    team = list(db.users.find({
        "organization_id": organization_id,
        "role": {"$in": ["org_admin", "team_user"]},
        "is_active": True,
    }).sort("_id", 1))
    if not team:
        return None
    # naive round robin: pick the member with fewest leads assigned
    counts = []
    for member in team:
        count = db.leads.count_documents({"organization_id": organization_id, "assigned_to": str(member["_id"])})
        counts.append((count, member))
    counts.sort(key=lambda x: x[0])
    return str(counts[0][1]["_id"]) if counts else None


def auto_assign(organization_id, lead: dict):
    db = get_db()
    rules = list(db.assignment_rules.find({
        "organization_id": organization_id, "is_active": True
    }).sort("priority", 1))
    for rule in rules:
        if _rule_matches(lead, rule):
            return rule.get("assignee_user_id")
    return _round_robin_assignee(organization_id)
