import bcrypt
import secrets
import time
from functools import wraps
from flask import session, redirect, url_for, request, jsonify, g
from app.extensions import get_db
from bson import ObjectId


# ---------- Password hashing ----------

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- IDs ----------

def new_id() -> str:
    return secrets.token_urlsafe(16)


def new_visitor_id() -> str:
    return "vis_" + secrets.token_urlsafe(18)


# ---------- Simple in-memory rate limiting (per-process; fine for single-instance MVP) ----------

_attempts = {}


def rate_limited(key: str, max_attempts: int = 8, window_seconds: int = 300) -> bool:
    """Returns True if the key has exceeded max_attempts within window_seconds."""
    now = time.time()
    bucket = _attempts.setdefault(key, [])
    # drop old entries
    bucket[:] = [t for t in bucket if now - t < window_seconds]
    if len(bucket) >= max_attempts:
        return True
    bucket.append(now)
    return False


# ---------- Session helpers ----------

def login_user(user: dict):
    session.clear()
    session.permanent = True
    session["user_id"] = str(user["_id"])
    session["role"] = user["role"]
    session["organization_id"] = user.get("organization_id")


def logout_user():
    session.clear()


def current_user():
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    if not user_id:
        g.user = None
        return None
    db = get_db()
    try:
        user = db.users.find_one({"_id": ObjectId(user_id), "is_active": True})
    except Exception:
        user = None
    g.user = user
    return user


# ---------- Decorators ----------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication_required"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "authentication_required"}), 401
                return redirect(url_for("auth.login"))
            if user["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "forbidden"}), 403
                return jsonify({"error": "forbidden"}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_scoped_organization_id():
    """Always derive organization_id from the server-side session, never trust the client."""
    user = current_user()
    if not user:
        return None
    return user.get("organization_id")
