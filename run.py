import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 6651))
    debug = os.environ.get("FLASK_ENV") != "production"
    # threaded=True is required for local dev: flask-sock holds each
    # WebSocket connection open on its own thread (ws.receive() blocks),
    # so the dev server needs to handle more than one request at a time or
    # a single open voice call would block every other page/request.
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)