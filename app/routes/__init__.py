import os
from flask import Flask
from flask_cors import CORS
from flask_sock import Sock
from app.config import Config
from app.extensions import close_db, get_db, init_indexes
#new file 
sock = Sock()



def create_app(config_class=Config):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)

    app.teardown_appcontext(close_db)

    with app.app_context():
        try:
            db = get_db()
            init_indexes(db)
        except Exception as e:
            app.logger.warning(f"Mongo not reachable at startup (will retry per-request): {e}")

    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.api_agents import api_agents_bp
    from app.routes.api_leads import api_leads_bp
    from app.routes.api_conversations import api_conversations_bp
    from app.routes.api_appointments import api_appointments_bp
    from app.routes.api_knowledge import api_knowledge_bp
    from app.routes.api_notifications import api_notifications_bp
    from app.routes.api_team import api_team_bp
    from app.routes.widget import widget_bp, register_widget_socket
    from app.routes.marketing import marketing_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_agents_bp)
    app.register_blueprint(api_leads_bp)
    app.register_blueprint(api_conversations_bp)
    app.register_blueprint(api_appointments_bp)
    app.register_blueprint(api_knowledge_bp)
    app.register_blueprint(api_notifications_bp)
    app.register_blueprint(api_team_bp)
    app.register_blueprint(widget_bp)
    app.register_blueprint(marketing_bp)

    # CORS is enabled ONLY for the public widget endpoints, since those are
    # called from arbitrary customer websites. Dashboard/admin/API routes are
    # intentionally left without CORS - they rely on same-origin session
    # cookies and must never be opened to other origins.
    CORS(
        app,
        resources={
            r"/api/widget/*": {"origins": "*"},
            r"/widget.js": {"origins": "*"},
        },
        supports_credentials=False,
    )

    # Real-time voice pipeline WebSocket route (/ws/widget/<agent_id>).
    # flask-sock registers routes directly against the app, so this is
    # wired up here rather than via a normal Blueprint.
    sock.init_app(app)
    register_widget_socket(sock)

    @app.context_processor
    def inject_globals():
        from app.security import current_user
        from datetime import datetime
        return {
            "app_name": app.config["APP_NAME"],
            "current_user": current_user(),
            "now_year": datetime.utcnow().year,
        }

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app