# Recepta — AI Website Receptionist SaaS

A multi-tenant SaaS platform where businesses create AI receptionists that chat and talk
with website visitors, answer questions from a RAG knowledge base (crawled website +
uploaded documents), capture and qualify leads, book appointments/site visits, notify
the team, and hand off to a human when needed.

Built with **Flask + MongoDB**, server-side sessions (no JWT), vanilla HTML/CSS/JS
dashboard, and a lightweight embeddable JS widget.

---

## 1. What's included

- **Platform admin dashboard** — create/suspend/delete organizations, manage users,
  create/edit pricing plans and features, view system logs and platform-wide usage,
  and a controlled "view as" (impersonation) mode for support.
- **Organization dashboard** — matches the reference design (dark theme, lime accent):
  stats, lead growth chart, lead sources, recent conversations, team performance.
- **Agent builder** — create an agent, configure system prompt/personality/greeting,
  lead capture fields, booking/site-visit/human-handoff toggles, widget appearance,
  and a live test-chat preview (test conversations never create real leads).
- **Knowledge base** — crawl a business website (sitemap discovery → same-domain
  crawl fallback → main-content extraction → chunking → embeddings) or upload
  PDF/DOCX/TXT/CSV documents. Every chunk is scoped to `organization_id` + `agent_id`
  so one business's knowledge can never leak into another's answers.
- **Conversation inbox** — a single inbox listing every chat *and* voice conversation;
  selecting one shows the full transcript (voice turns are shown as their transcribed
  text, tagged "Voice").
- **Leads** — status pipeline, manual/automatic assignment (rule-based + round robin),
  notes, and the source conversation inline on the lead page.
- **Appointments** — simple built-in availability/booking (swap for Google
  Calendar/Outlook/Calendly later without touching the agent's tool interface).
- **Notifications** — in-app notification center + unread badge; browser-push and
  email dispatch hooks are stubbed and ready to wire up to real providers.
- **Public embeddable widget** (`widget.js`) — chat + voice (mic recording →
  Deepgram STT → LLM → TTS playback), greeting bubble with configurable delay,
  theme/color/position config, and **visitor IP capture** (`X-Forwarded-For`-aware)
  so every conversation/visitor record on the dashboard carries the visitor's IP.
- **Provider abstractions** — `llm_service`, `embedding_service`, `tts_service`,
  `stt_service`, `storage_service` are all thin interfaces. The app ships with a
  **local embedding fallback** (works with zero external keys) and a text-only
  fallback LLM response, so the whole flow is runnable and demoable before you add
  any API keys — then swap providers by editing one file each.
- **Backend agent tools** — `search_knowledge`, `capture_lead`, `check_availability`,
  `book_appointment`, `request_site_visit`, `transfer_to_human`, etc. The LLM can only
  *request* these; only `app/services/agent_tools.py` ever touches the database.
- **Security** — bcrypt password hashing, HttpOnly/SameSite server-side sessions
  (no JWT), rate-limited login, every organization-owned query scoped server-side
  from the session (never trusts a client-supplied `organization_id`), file type/size
  validation, crawler domain/URL/depth/timeout limits, and a prompt-injection
  guard so crawled website/document content is treated as data, never instructions.

---

## 2. Project structure

```text
recepta/
├── app/
│   ├── __init__.py             # app factory, blueprint registration
│   ├── config.py                # all env-driven configuration
│   ├── extensions.py            # Mongo connection + indexes
│   ├── models.py                 # document builders/serializers
│   ├── security.py               # bcrypt, sessions, decorators, rate limiting
│   ├── routes/
│   │   ├── auth.py               # login/register/logout/password reset
│   │   ├── admin.py              # platform admin: orgs, users, plans, logs
│   │   ├── dashboard.py          # organization dashboard pages
│   │   ├── api_agents.py         # agent CRUD, publish/pause, test-chat
│   │   ├── api_leads.py          # lead status/assignment/notes/rules
│   │   ├── api_conversations.py  # conversation transcripts (chat + voice)
│   │   ├── api_appointments.py
│   │   ├── api_knowledge.py      # website crawl + document upload ingestion
│   │   ├── api_notifications.py
│   │   ├── api_team.py
│   │   └── widget.py             # PUBLIC widget config/session/chat/voice/lead
│   ├── services/
│   │   ├── llm_service.py        # Groq / Mistral / OpenRouter abstraction
│   │   ├── embedding_service.py  # pluggable, local fallback included
│   │   ├── tts_service.py        # Sarvam (swap-in-place)
│   │   ├── stt_service.py        # Deepgram
│   │   ├── rag_service.py        # chunking + scoped retrieval
│   │   ├── crawler_service.py    # sitemap discovery + safe crawl
│   │   ├── document_service.py   # PDF/DOCX/TXT/CSV text extraction
│   │   ├── storage_service.py    # Supabase Storage abstraction
│   │   ├── chat_service.py       # orchestrates a visitor turn end-to-end
│   │   ├── agent_tools.py        # the ONLY code that executes agent actions
│   │   ├── assignment_service.py
│   │   ├── notification_service.py
│   │   └── usage_service.py
│   ├── templates/                # server-rendered Jinja pages (vanilla HTML/CSS/JS)
│   └── static/
│       ├── css/style.css         # dark theme + lime accent design system
│       ├── js/dashboard.js       # dashboard interactivity
│       ├── js/widget-loader.js   # THE public widget (served as /widget.js)
│       └── images/               # logo-icon.png, logo-wordmark.png, favicon.png
├── migrations/seed.py            # creates platform admin + default plans + demo org
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── run.py
```

---

## 3. Quick start (Docker)

```bash
cp .env.example .env
# then edit .env — at minimum set SECRET_KEY to a long random string.
# Everything else (LLM/TTS/STT/Supabase keys) is optional to start: the app
# runs with safe local fallbacks so you can click through the whole product
# before wiring up paid providers.

docker build -t recepta .
docker compose up -d --build

# create the platform admin + default plans + a demo org:
docker compose exec web python migrations/seed.py
```

App is now running at **http://localhost:6651**.

Default seeded logins (override via `.env` before seeding):


**Change these passwords immediately in any non-local environment.**

### Common Docker commands

```bash
docker compose up -d --build     # build & start (web + mongo)
docker compose logs -f web       # tail app logs
docker compose stop              # stop containers, keep them
docker compose start             # resume stopped containers
docker compose down              # stop & remove containers (keeps the mongo volume)
docker compose down -v           # stop & remove containers AND the mongo data volume
docker build -t recepta . && docker run -p 6651:6651 --env-file .env recepta   # run the app image alone (needs an external MONGO_URI)
docker rm -f recepta-web recepta-mongo   # force-remove containers by name
```

---

## 4. Running locally without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run a local MongoDB, or point MONGO_URI in .env at MongoDB Atlas
cp .env.example .env

python migrations/seed.py
python run.py   # serves on http://localhost:6651
```

---

## 5. Using the product

1. **Register a business** at `/register`, or have the platform admin create one
   from `/admin/organizations`.
2. **Create an agent** (`Dashboard → Agents → Create New Agent`): business info,
   then configure system prompt/personality/greeting, lead capture fields, and
   widget appearance on the agent's tabs.
3. **Add knowledge**: `Dashboard → Knowledge Base` — enter the business website
   to crawl it, and/or upload PDFs/DOCX/TXT/CSV.
4. **Test it** in the agent page's Live Preview panel (always test-mode; never
   creates a real lead).
5. **Publish** the agent, copy the generated `<script>` embed code from the
   Embed Code tab, and paste it before `</body>` on the business site. You can
   also preview it instantly at `/widget/preview/<agent_id>`.
6. Visitors chat or talk with the widget → leads land in **Leads**, notifications
   fire, and every conversation (chat or voice, with the visitor's IP) shows up
   in **Conversations** with its full transcript.
7. **Team** members can be added under `Dashboard → Team`; they can view/update
   leads assigned to them but cannot manage agents, billing, or org settings —
   enforced server-side via `roles_required`, not just hidden in the UI.

---

## 6. Wiring up real providers

Everything works out of the box with safe fallbacks. To go to production, set
these in `.env` (see `.env.example` for the full list):

- `GROQ_API_KEY` / `MISTRAL_API_KEY` / `OPENROUTER_API_KEY` + `LLM_PROVIDER`
- `DEEPGRAM_API_KEY` (speech-to-text)
- `TTS_API_KEY` + `TTS_PROVIDER` (defaults to Sarvam)
- `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_BUCKET` (file storage)
- `EMBEDDING_PROVIDER` — ships with `local` (zero-dependency hashing embedder);
  wire in a real embedding API in `app/services/embedding_service.py` when ready,
  and/or point `rag_service.retrieve()` at a MongoDB Atlas `$vectorSearch` index
  once your knowledge base is large enough to need it.

No code in `app/routes/` or `app/services/chat_service.py` needs to change when
you swap a provider — only the relevant file in `app/services/`.

---

## 7. Security notes

- Sessions are server-side (Flask session cookie, HttpOnly, SameSite=Lax,
  Secure in production) — **no JWT** is used anywhere.
- Every dashboard/API route resolves `organization_id` from the authenticated
  session (`get_scoped_organization_id()`), never from the request body/query
  string, so one organization can never read or write another's data.
- Passwords are hashed with bcrypt; plaintext passwords are never stored or logged.
- The website crawler is restricted to the target domain, with hard caps on URL
  count, crawl depth, and per-request timeout (`CRAWL_MAX_URLS`,
  `CRAWL_MAX_DEPTH`, `CRAWL_TIMEOUT_SECONDS` in `.env`).
- Retrieved website/document content is explicitly labelled as untrusted data in
  the system prompt (`chat_service.PLATFORM_SAFETY_PROMPT`) so embedded
  instructions in a crawled page can't override the agent's behavior.
- `.env` is git-ignored; never commit real API keys or the Mongo URI.

---

## 8. Notes on scope

This is a complete, runnable MVP covering Phases 1–6 of the product's own roadmap
(auth/orgs/agents/widget → crawler/RAG → chat/leads/notifications → voice/TTS/STT →
appointments/assignment → analytics/usage/admin). A few things are intentionally
left as clearly-marked extension points rather than fully built out, since they
depend on accounts/credentials only you can provide:

- **Payments/subscriptions** — `organizations.billing_customer_id` /
  `billing_subscription_id` fields and the `/dashboard/billing` page are in place;
  wire in Stripe (or your provider of choice) without touching lead/agent logic.
- **Browser push / email dispatch** — `notification_service._dispatch_browser_push`
  and `_dispatch_email` are stubs with the interface already wired through the
  whole app (in-app notifications work today); add `pywebpush`/VAPID keys and an
  SMTP/email API call to go live.
- **Calendar integrations** — `agent_tools.check_availability`/`book_appointment`
  use simple built-in slot logic; swap in Google Calendar/Outlook/Calendly behind
  the same function signatures when ready.
