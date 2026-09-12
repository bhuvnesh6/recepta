FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_PORT=6651

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 6651

# -k gevent is required, not optional: the real-time voice pipeline holds a
# long-lived WebSocket per active call (browser mic <-> Deepgram/Groq/Sarvam),
# and the default sync gunicorn worker can only serve ONE such connection at
# a time - every other request (including the dashboard) would hang behind
# it. gevent monkey-patches the process into cooperative greenlets, so one
# worker can hold many concurrent WebSocket + HTTP connections at once. Bump
# --workers if you need more than one process (each still handles many
# concurrent greenlets on its own).
CMD ["gunicorn", "--worker-class", "gevent", "--workers", "1", "--bind", "0.0.0.0:6651", "--timeout", "120", "run:app"]