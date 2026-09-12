from flask import Blueprint, request, jsonify, send_from_directory, current_app, Response, render_template
from bson import ObjectId

from app.extensions import get_db
from app.models import build_conversation, build_message, build_visitor, serialize, now
from app.security import new_visitor_id
from app.services.chat_service import handle_visitor_message
from app.services.stt_service import get_stt_provider
from app.services.tts_service import get_tts_provider
from app.services import usage_service

widget_bp = Blueprint("widget", __name__)


def _client_ip():
    """Respect a reverse proxy's X-Forwarded-For while defaulting to remote_addr."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def _touch_visitor(organization_id, visitor_id):
    db = get_db()
    existing = db.visitors.find_one({"visitor_id": visitor_id})
    if existing:
        db.visitors.update_one({"visitor_id": visitor_id}, {
            "$set": {"last_seen_at": now(), "ip_address": _client_ip()},
            "$inc": {"visit_count": 1},
        })
    else:
        doc = build_visitor(visitor_id, organization_id, ip_address=_client_ip(),
                             user_agent=request.headers.get("User-Agent", ""))
        db.visitors.insert_one(doc)


@widget_bp.get("/widget/preview/<agent_id>")
def widget_preview(agent_id):
    db = get_db()
    agent = db.agents.find_one({"_id": ObjectId(agent_id)})
    return render_template("widget/embed_demo.html", agent_id=agent_id,
                            agent_name=agent["business_name"] if agent else None,
                            widget_base_url=f"https://{request.host}")


@widget_bp.get("/widget.js")
def widget_js():
    return send_from_directory(current_app.static_folder + "/js", "widget-loader.js",
                                mimetype="application/javascript")


@widget_bp.get("/api/widget/config/<agent_id>")
def widget_config(agent_id):
    db = get_db()
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
    if not agent:
        return jsonify({"error": "agent_not_available"}), 404
    return jsonify({
        "agent_id": str(agent["_id"]),
        "name": agent["name"],
        "business_name": agent["business_name"],
        "greeting_text": agent.get("greeting_text"),
        "greeting_audio_url": agent.get("greeting_audio_url"),
        "language": agent.get("language", "en"),
        "widget": agent.get("widget", {}),
        "tools_enabled": agent.get("tools_enabled", {}),
    })


@widget_bp.post("/api/widget/session")
def widget_session():
    """Issue or resume an anonymous visitor id and open a conversation."""
    db = get_db()
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    channel = data.get("channel", "chat")
    visitor_id = data.get("visitor_id") or new_visitor_id()

    agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
    if not agent:
        return jsonify({"error": "agent_not_available"}), 404

    _touch_visitor(agent["organization_id"], visitor_id)

    conv = build_conversation(agent["organization_id"], agent_id, visitor_id, channel=channel)
    conv["visitor_ip"] = _client_ip()
    result = db.conversations.insert_one(conv)

    return jsonify({"visitor_id": visitor_id, "conversation_id": str(result.inserted_id)})


@widget_bp.post("/api/widget/chat")
def widget_chat():
    db = get_db()
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    conversation_id = data.get("conversation_id")
    message = (data.get("message") or "").strip()
    if not (agent_id and conversation_id and message):
        return jsonify({"error": "invalid_request"}), 400

    agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
    conversation = db.conversations.find_one({"_id": ObjectId(conversation_id), "agent_id": agent_id})
    if not agent or not conversation:
        return jsonify({"error": "not_found"}), 404

    result = handle_visitor_message(agent["organization_id"], agent, conversation_id, message,
                                     is_test=conversation.get("is_test", False))
    usage_service.track(agent["organization_id"], agent_id, "ai_messages", 1)
    return jsonify(result)


@widget_bp.post("/api/widget/voice")
def widget_voice():
    """Batch voice fallback (record -> stop -> send) for browsers/situations
    where the streaming WebSocket pipeline isn't available. The main voice
    experience is the /ws/widget/<agent_id> real-time pipeline below."""
    db = get_db()
    agent_id = request.form.get("agent_id")
    conversation_id = request.form.get("conversation_id")
    audio_file = request.files.get("audio")
    if not (agent_id and conversation_id and audio_file):
        return jsonify({"error": "invalid_request"}), 400

    agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
    conversation = db.conversations.find_one({"_id": ObjectId(conversation_id), "agent_id": agent_id})
    if not agent or not conversation:
        return jsonify({"error": "not_found"}), 404

    audio_bytes = audio_file.read()
    stt = get_stt_provider()
    transcript = stt.transcribe(audio_bytes, audio_file.mimetype or "audio/webm")
    if not transcript:
        return jsonify({"error": "could_not_transcribe"}), 422

    result = handle_visitor_message(agent["organization_id"], agent, conversation_id, transcript,
                                     is_test=conversation.get("is_test", False))
    usage_service.track(agent["organization_id"], agent_id, "voice_minutes", round(len(audio_bytes) / 240000, 2))

    tts = get_tts_provider()
    audio_reply = tts.generate(result["reply"], voice=agent.get("voice", {}).get("voice_id", "default"),
                                language=agent.get("language", "en"))
    import base64
    result["transcript"] = transcript
    result["audio_base64"] = base64.b64encode(audio_reply).decode("utf-8") if audio_reply else None
    return jsonify(result)


@widget_bp.post("/api/widget/lead")
def widget_lead_capture():
    """Direct lead capture endpoint used by the widget's lead form (in
    addition to the AI capturing leads conversationally via tools)."""
    from app.services.agent_tools import capture_lead
    db = get_db()
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    conversation_id = data.get("conversation_id")
    agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
    conversation = db.conversations.find_one({"_id": ObjectId(conversation_id), "agent_id": agent_id})
    if not agent or not conversation:
        return jsonify({"error": "not_found"}), 404
    lead_id = capture_lead(
        agent["organization_id"], agent_id, conversation_id,
        name=data.get("name"), email=data.get("email"), phone=data.get("phone"),
        requirement=data.get("requirement"), location=data.get("location"),
        budget=data.get("budget"), is_test=conversation.get("is_test", False),
    )
    return jsonify({"lead_id": lead_id})


# ============================================================
# Real-time streaming voice pipeline (WebSocket)
# ============================================================
_VOICE_CONFIG_KEYS = [
    "DEEPGRAM_API_KEY", "DEEPGRAM_STREAMING_MODEL", "DEEPGRAM_STREAMING_LANGUAGE",
    "GROQ_API_KEY", "TTS_API_KEY", "VOICE_TTS_MODEL", "VOICE_TTS_SPEAKER", "VOICE_TTS_PACE",
    "VOICE_MIC_SAMPLE_RATE", "VOICE_TTS_SAMPLE_RATE",
    "VOICE_RESPONSE_PAUSE_SECS", "VOICE_RESPONSE_PAUSE_JITTER_SECS",
    "VOICE_SHORT_UTTERANCE_MAX_WORDS", "VOICE_SHORT_UTTERANCE_PAUSE_SECS",
    "VOICE_BARGE_IN_GRACE_SECS", "VOICE_BARGE_IN_CONFIRM_MIN_CHARS",
    "VOICE_BARGE_IN_CONFIRM_TIMEOUT_SECS",
]


def register_widget_socket(sock):
    """Registers /ws/widget/<agent_id>, the real-time streaming voice
    endpoint. Called once from the app factory (flask-sock binds routes
    directly to the app, not through a Blueprint).

    The browser must call POST /api/widget/session first (same as the
    batch voice/chat flow) to get a conversation_id + visitor_id - that
    keeps visitor IP capture, multi-tenant scoping, and conversation
    creation on one code path, and is passed here as query params:

        wss://.../ws/widget/<agent_id>?conversation_id=...&visitor_id=...
    """
    import json as _json
    from app.services.voice_stream_service import WidgetVoiceSession

    @sock.route("/ws/widget/<agent_id>")
    def widget_voice_ws(ws, agent_id):
        db = get_db()
        conversation_id = request.args.get("conversation_id")
        visitor_id = request.args.get("visitor_id")

        agent = db.agents.find_one({"_id": ObjectId(agent_id), "status": "live"})
        conversation = None
        if conversation_id:
            conversation = db.conversations.find_one({"_id": ObjectId(conversation_id), "agent_id": agent_id})

        if not agent or not conversation:
            try:
                ws.send(_json.dumps({"type": "error", "message": "Voice session not available. Refresh and try again."}))
            except Exception:
                pass
            return

        cfg = {k: current_app.config.get(k) for k in _VOICE_CONFIG_KEYS}
        missing = [k for k in ("DEEPGRAM_API_KEY", "GROQ_API_KEY") if not cfg.get(k)]
        if missing:
            try:
                ws.send(_json.dumps({"type": "error",
                                      "message": f"Voice pipeline not configured yet ({', '.join(missing)} missing)."}))
            except Exception:
                pass
            return

        session = WidgetVoiceSession(ws, db, cfg, agent["organization_id"], agent, conversation_id, visitor_id)
        if not session.start():
            return

        db.conversations.update_one({"_id": ObjectId(conversation_id)}, {"$set": {"channel": "voice"}})

        session._send_json({"type": "ready"})
        greeting = agent.get("greeting_text") or "Hi! How can I help you today?"
        session.speak(greeting)

        log_prefix = f"[voice_ws:{conversation_id}]"
        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break
                if isinstance(msg, (bytes, bytearray)):
                    session.feed_audio(bytes(msg))
                    continue
                try:
                    payload = _json.loads(msg)
                except Exception:
                    continue
                if payload.get("type") == "ping":
                    session._send_json({"type": "pong"})
        except Exception as e:
            current_app.logger.warning(f"{log_prefix} loop error: {e}")
        finally:
            session.close()