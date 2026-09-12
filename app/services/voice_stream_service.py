"""
Real-time streaming voice pipeline for the embeddable widget's "Talk" tab -
architecturally mirrors Eva's voice bot:

    browser mic (PCM16 /16kHz, continuous)
        -> Deepgram streaming STT (live transcription + VAD)
        -> natural turn-taking pause (waits for the visitor to actually
           finish, with a jitter so replies don't land on the same beat
           every time)
        -> RAG retrieval scoped to (organization_id, agent_id) for the
           finished utterance
        -> Groq streaming LLM (sentence-by-sentence, so TTS can start
           speaking the first sentence before the model has finished
           thinking of the rest)
        -> Sarvam streaming TTS
        -> PCM16 /22050Hz audio frames sent back to the browser
        -> browser schedules and plays them, and can barge in (stop Eva
           mid-sentence) - a real interruption needs actual transcribed
           words, not just any mic noise, to avoid Eva stopping every time
           a visitor coughs or bumps their desk.

One WidgetVoiceSession per WebSocket connection. Every DB write goes
through the `self.db` handle captured once at connect time (pymongo
Database/Collection objects are thread-safe, so the LLM/TTS background
threads reuse it directly rather than needing a Flask app/request context,
which threading.Thread does not inherit).

Differences from a plain chat turn (chat_service.py):
  - The knowledge base and business system prompt are shared with the REST
    chat pipeline (chat_service.build_system_prompt) so voice and chat
    never give a visitor conflicting answers.
  - Because there's no OpenAI-style tool-calling loop over a WebSocket
    stream (adding an actual function-calling handshake mid-stream would
    stall speech), agent actions are triggered by the model emitting a
    short inline tag at the end of a sentence, e.g.:
        CAPTURE_LEAD: name=John Smith|phone=555-1234|requirement=AC repair
        BOOK_APPOINTMENT: 2026-09-20 14:00
        TRANSFER_HUMAN: caller asked for a manager
    These tags are parsed out, executed via agent_tools.py (never spoken
    aloud), and everything else is spoken normally - the same pattern Eva
    uses for BOOK_MEETING.
"""
import json
import math
import array
import queue
import random
import re
import threading
import time

import requests
from bson import ObjectId

from app.models import build_message, build_usage_event, now
from app.services import rag_service
from app.services.chat_service import build_system_prompt
from app.services.agent_tools import capture_lead, book_appointment, transfer_to_human

SENTENCE_END_RE = re.compile(r"([.!?\n])")
SPEAKABLE_RE = re.compile(r"[A-Za-z0-9]")
CAPTURE_LEAD_RE = re.compile(r"CAPTURE_LEAD:\s*(.+)")
BOOK_APPOINTMENT_RE = re.compile(r"BOOK_APPOINTMENT:\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})")
TRANSFER_HUMAN_RE = re.compile(r"TRANSFER_HUMAN:\s*(.*)")

TOOL_TAG_INSTRUCTIONS = """You can take three actions during this live voice call by outputting
EXACTLY one line in one of these formats and nothing else on that line
(never say the line out loud, it is processed automatically):

CAPTURE_LEAD: name=<name>|email=<email>|phone=<phone>|requirement=<what they need>
  - Use this as soon as you have the visitor's name and at least one way to
    reach them (email or phone). Include only the fields you actually have.
BOOK_APPOINTMENT: YYYY-MM-DD HH:MM (24-hour clock, UTC)
  - Only after CAPTURE_LEAD has already been sent once this call, and the
    visitor has confirmed one specific date and time.
TRANSFER_HUMAN: <short reason>
  - When the visitor explicitly asks for a human, or you cannot help them.

After any of these, continue the conversation normally in your next reply
based on the result you're given."""


def log(stage: str, msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [VOICE:{stage}] {msg}", flush=True)


def is_speakable(text: str) -> bool:
    return bool(SPEAKABLE_RE.search(text))


def _rms_pcm16(data: bytes) -> float:
    usable_len = len(data) - (len(data) % 2)
    if usable_len < 2:
        return 0.0
    samples = array.array('h')
    samples.frombytes(data[:usable_len])
    if not samples:
        return 0.0
    total = sum(s * s for s in samples)
    return math.sqrt(total / len(samples))


class WidgetVoiceSession:
    def __init__(self, ws, db, cfg, organization_id, agent, conversation_id, visitor_id):
        """
        ws: the flask-sock WebSocket connection
        db: pymongo Database handle, captured once while a valid Flask
            context existed (reused directly by background threads)
        cfg: a plain dict snapshot of the relevant current_app.config
             values, captured up front so threads never need `current_app`
        """
        self.ws = ws
        self.db = db
        self.cfg = cfg
        self.organization_id = organization_id
        self.agent = agent
        self.agent_id = str(agent["_id"])
        self.conversation_id = conversation_id
        self.visitor_id = visitor_id

        self.ws_lock = threading.Lock()
        self.stop_event = threading.Event()

        # --- barge-in / turn-taking state (mirrors Eva's EvaSession) ---
        self.eva_speaking = threading.Event()
        self.interrupt_flag = threading.Event()
        self.pending_lock = threading.Lock()
        self.pending_transcript = ""
        self.pending_timer = None
        self.barge_in_grace_until = 0.0
        self.barge_in_candidate = threading.Event()
        self.barge_in_candidate_lock = threading.Lock()
        self.barge_in_candidate_timer = None
        self.turn_active = False

        self.user_text_q = queue.Queue()
        self.sentence_q = queue.Queue()

        self.history = []
        self.captured_lead_id = None
        self.connected_at = time.time()

        tool_instructions = TOOL_TAG_INSTRUCTIONS if agent.get("tools_enabled", {}).get("lead_capture", True) else None
        self.system_prompt = build_system_prompt(agent, voice_mode=True, tool_tag_instructions=tool_instructions)

        self.deepgram = None
        self.dg_connection = None
        self.sarvam = None

    # ---------- outbound ----------
    def _send_json(self, obj):
        with self.ws_lock:
            try:
                self.ws.send(json.dumps(obj))
            except Exception:
                pass

    def _send_audio(self, audio_bytes: bytes):
        with self.ws_lock:
            try:
                self.ws.send(audio_bytes)
            except Exception:
                pass

    # ---------- barge-in ----------
    def _interrupt_playback(self):
        self.interrupt_flag.set()
        with self.sentence_q.mutex:
            self.sentence_q.queue.clear()
        with self.barge_in_candidate_lock:
            self.barge_in_candidate.clear()
            if self.barge_in_candidate_timer:
                self.barge_in_candidate_timer.cancel()
                self.barge_in_candidate_timer = None
        self.turn_active = False
        self._send_json({"type": "interrupt"})
        self._send_json({"type": "status", "state": "listening"})
        self.eva_speaking.clear()

    # ---------- Deepgram callbacks ----------
    def _dg_open(self, *_a, **_k):
        log("STT", f"[{self.conversation_id}] Deepgram connection open.")

    def _dg_speech_started(self, *_a, **_k):
        if time.time() < self.barge_in_grace_until:
            return
        if not (self.eva_speaking.is_set() or not self.sentence_q.empty()):
            return
        self._arm_barge_in_candidate("vad")

    def _check_volume_barge_in(self, raw_audio: bytes):
        if time.time() < self.barge_in_grace_until:
            return
        if not (self.eva_speaking.is_set() or not self.sentence_q.empty()):
            return
        if self.barge_in_candidate.is_set():
            return
        rms = _rms_pcm16(raw_audio)
        if rms >= 600:
            self._arm_barge_in_candidate(f"volume({rms:.0f})")

    def _arm_barge_in_candidate(self, source: str):
        with self.barge_in_candidate_lock:
            already = self.barge_in_candidate.is_set()
            self.barge_in_candidate.set()
            if self.barge_in_candidate_timer:
                self.barge_in_candidate_timer.cancel()
            self.barge_in_candidate_timer = threading.Timer(
                self.cfg["VOICE_BARGE_IN_CONFIRM_TIMEOUT_SECS"], self._clear_barge_in_candidate
            )
            self.barge_in_candidate_timer.daemon = True
            self.barge_in_candidate_timer.start()
        if not already:
            log("BARGE-IN", f"[{self.conversation_id}] candidate armed via {source}")

    def _clear_barge_in_candidate(self):
        with self.barge_in_candidate_lock:
            self.barge_in_candidate.clear()
            self.barge_in_candidate_timer = None

    def _dg_transcript(self, *_a, result=None, **_k):
        if result is None:
            return
        transcript = result.channel.alternatives[0].transcript
        if not transcript:
            return

        if self.barge_in_candidate.is_set() and len(transcript.strip()) >= self.cfg["VOICE_BARGE_IN_CONFIRM_MIN_CHARS"]:
            with self.barge_in_candidate_lock:
                self.barge_in_candidate.clear()
                if self.barge_in_candidate_timer:
                    self.barge_in_candidate_timer.cancel()
                    self.barge_in_candidate_timer = None
            if self.eva_speaking.is_set() or not self.sentence_q.empty():
                with self.pending_lock:
                    if self.pending_timer:
                        self.pending_timer.cancel()
                        self.pending_timer = None
                log("MAIN", f"[{self.conversation_id}] Barge-in confirmed.")
                self._interrupt_playback()

        if result.is_final:
            self._send_json({"type": "user_transcript", "text": transcript, "final": True})
            self._queue_with_pause(transcript)
        else:
            self._send_json({"type": "user_transcript", "text": transcript, "final": False})

    def _dg_error(self, *_a, error=None, **_k):
        log("STT", f"ERROR: {error}")

    def _dg_close(self, *_a, **_k):
        log("STT", f"[{self.conversation_id}] Deepgram connection closed.")

    # ---------- natural turn-taking pause ----------
    def _queue_with_pause(self, transcript: str):
        with self.pending_lock:
            self.pending_transcript = (self.pending_transcript + " " + transcript).strip()
            if self.pending_timer:
                self.pending_timer.cancel()
            word_count = len(self.pending_transcript.split())
            base_delay = (
                self.cfg["VOICE_SHORT_UTTERANCE_PAUSE_SECS"]
                if word_count <= self.cfg["VOICE_SHORT_UTTERANCE_MAX_WORDS"]
                else self.cfg["VOICE_RESPONSE_PAUSE_SECS"]
            )
            delay = base_delay + random.uniform(0, self.cfg["VOICE_RESPONSE_PAUSE_JITTER_SECS"])
            self.pending_timer = threading.Timer(delay, self._flush_pending_transcript)
            self.pending_timer.daemon = True
            self.pending_timer.start()

    def _flush_pending_transcript(self):
        with self.pending_lock:
            text = self.pending_transcript.strip()
            self.pending_transcript = ""
            self.pending_timer = None
        if text:
            self.user_text_q.put(text)

    # ---------- lifecycle ----------
    def start(self):
        from deepgram import (
            DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents, LiveOptions,
        )
        from sarvamai import SarvamAI

        dg_options = DeepgramClientOptions(options={"keepalive": "true"})
        self.deepgram = DeepgramClient(self.cfg["DEEPGRAM_API_KEY"], dg_options)
        self.dg_connection = self.deepgram.listen.websocket.v("1")
        self.dg_connection.on(LiveTranscriptionEvents.Open, self._dg_open)
        self.dg_connection.on(LiveTranscriptionEvents.Transcript, self._dg_transcript)
        self.dg_connection.on(LiveTranscriptionEvents.SpeechStarted, self._dg_speech_started)
        self.dg_connection.on(LiveTranscriptionEvents.Error, self._dg_error)
        self.dg_connection.on(LiveTranscriptionEvents.Close, self._dg_close)

        options = LiveOptions(
            model=self.cfg["DEEPGRAM_STREAMING_MODEL"],
            language=self.cfg["DEEPGRAM_STREAMING_LANGUAGE"],
            smart_format=True,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            encoding="linear16",
            sample_rate=self.cfg["VOICE_MIC_SAMPLE_RATE"],
            channels=1,
        )
        if not self.dg_connection.start(options):
            self._send_json({"type": "error", "message": "Could not start speech recognition."})
            return False

        self.sarvam = SarvamAI(api_subscription_key=self.cfg["TTS_API_KEY"]) if self.cfg["TTS_API_KEY"] else None

        threading.Thread(target=self._llm_loop, daemon=True, name="VoiceLLM").start()
        threading.Thread(target=self._tts_loop, daemon=True, name="VoiceTTS").start()
        return True

    def feed_audio(self, data: bytes):
        try:
            self._check_volume_barge_in(data)
        except Exception as e:
            log("BARGE-IN", f"volume check error: {e}")
        try:
            self.dg_connection.send(data)
        except Exception as e:
            log("STT", f"send error: {e}")

    def _enqueue_sentence(self, text: str):
        if self.sentence_q.empty() and not self.turn_active:
            self.barge_in_grace_until = time.time() + self.cfg["VOICE_BARGE_IN_GRACE_SECS"]
        self.turn_active = True
        self.sentence_q.put(text)

    def speak(self, text: str):
        """Queue a line straight to TTS, bypassing the LLM (e.g. the opening greeting)."""
        self._enqueue_sentence(text)

    def close(self):
        self.stop_event.set()
        with self.pending_lock:
            if self.pending_timer:
                self.pending_timer.cancel()
                self.pending_timer = None
        with self.barge_in_candidate_lock:
            if self.barge_in_candidate_timer:
                self.barge_in_candidate_timer.cancel()
            self.barge_in_candidate.clear()
        try:
            if self.dg_connection:
                self.dg_connection.finish()
        except Exception:
            pass

        # Track voice minutes for this call on the way out.
        duration_secs = time.time() - self.connected_at
        try:
            self.db.usage_events.insert_one(
                build_usage_event(self.organization_id, self.agent_id, "voice_minutes", round(duration_secs / 60, 2))
            )
            self.db.conversations.update_one(
                {"_id": ObjectId(self.conversation_id)}, {"$set": {"updated_at": now()}}
            )
        except Exception as e:
            log("MAIN", f"close() bookkeeping failed: {e}")

    # ---------- tool tag handling ----------
    def _handle_tool_tags(self, sentence: str) -> str:
        """Strips and executes any inline action tag found in `sentence`,
        returning the sentence with the tag line removed (so it's never
        spoken aloud)."""
        m = CAPTURE_LEAD_RE.search(sentence)
        if m:
            fields = {}
            for part in m.group(1).split("|"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    fields[k.strip().lower()] = v.strip()
            try:
                self.captured_lead_id = capture_lead(
                    self.organization_id, self.agent_id, self.conversation_id,
                    name=fields.get("name"), email=fields.get("email"),
                    phone=fields.get("phone"), requirement=fields.get("requirement"),
                    db=self.db,
                )
                log("LEAD", f"[{self.conversation_id}] captured lead {self.captured_lead_id}")
            except Exception as e:
                log("LEAD", f"capture failed: {e}")
            sentence = CAPTURE_LEAD_RE.sub("", sentence).strip()

        m = BOOK_APPOINTMENT_RE.search(sentence)
        if m:
            if self.captured_lead_id:
                start_str = f"{m.group(1)} {m.group(2)}"
                try:
                    result = book_appointment(self.organization_id, self.agent_id, self.captured_lead_id,
                                               start_str, db=self.db)
                    self.history.append({
                        "role": "system",
                        "content": f"[Booking result: {'confirmed' if result.get('success') else 'unavailable'}]",
                    })
                except Exception as e:
                    log("BOOKING", f"failed: {e}")
            else:
                self.history.append({"role": "system", "content": "[Booking skipped: no lead captured yet]"})
            sentence = BOOK_APPOINTMENT_RE.sub("", sentence).strip()

        m = TRANSFER_HUMAN_RE.search(sentence)
        if m:
            try:
                transfer_to_human(self.organization_id, self.conversation_id, reason=m.group(1), db=self.db)
            except Exception as e:
                log("HANDOFF", f"failed: {e}")
            sentence = TRANSFER_HUMAN_RE.sub("", sentence).strip()

        return sentence

    # ---------- LLM loop ----------
    def _llm_loop(self):
        from app.services.llm_service import GroqProvider
        llm = GroqProvider(self.cfg["GROQ_API_KEY"])

        while not self.stop_event.is_set():
            try:
                user_text = self.user_text_q.get(timeout=0.5)
            except Exception:
                continue

            self.interrupt_flag.clear()
            self._send_json({"type": "status", "state": "thinking"})

            # Persist the visitor's turn and pull scoped RAG context for it.
            try:
                self.db.messages.insert_one(build_message(self.conversation_id, "visitor", user_text))
            except Exception as e:
                log("DB", f"save visitor message failed: {e}")

            try:
                chunks = rag_service.retrieve(self.organization_id, self.agent_id, user_text, db=self.db)
                context_block = rag_service.build_context_block(chunks)
            except Exception as e:
                log("RAG", f"retrieve failed: {e}")
                chunks = []
                context_block = ""

            self.history.append({"role": "user", "content": user_text})

            messages = [{"role": "system", "content": self.system_prompt}]
            if context_block:
                messages.append({"role": "system", "content": context_block})
            messages.extend(self.history[-16:])

            buffer, full_reply = "", ""
            try:
                for delta in llm.stream(messages):
                    if self.interrupt_flag.is_set():
                        break
                    buffer += delta
                    full_reply += delta
                    self._send_json({"type": "assistant_delta", "text": delta})

                    parts = SENTENCE_END_RE.split(buffer)
                    complete, i = "", 0
                    while i + 1 < len(parts):
                        complete += parts[i] + parts[i + 1]
                        i += 2
                    remainder = parts[i] if i < len(parts) else ""

                    sentence = complete.strip()
                    if sentence:
                        sentence = self._handle_tool_tags(sentence)
                        if sentence and is_speakable(sentence):
                            self._enqueue_sentence(sentence)
                    buffer = remainder
            except Exception as e:
                log("LLM", f"ERROR: {e}")
                self._send_json({"type": "error", "message": "I'm having trouble responding right now."})
                continue

            if not self.interrupt_flag.is_set():
                tail = buffer.strip()
                if tail:
                    tail = self._handle_tool_tags(tail)
                    if tail and is_speakable(tail):
                        self._enqueue_sentence(tail)

            if full_reply.strip():
                try:
                    self.db.messages.insert_one(
                        build_message(self.conversation_id, "assistant", full_reply.strip(),
                                      {"rag_chunks": len(chunks)})
                    )
                    self.db.usage_events.insert_one(
                        build_usage_event(self.organization_id, self.agent_id, "ai_messages", 1)
                    )
                except Exception as e:
                    log("DB", f"save assistant message failed: {e}")

            self.history.append({"role": "assistant", "content": full_reply})
            if len(self.history) > 16:
                self.history = self.history[-16:]
            self._send_json({"type": "assistant_done", "text": full_reply})

    # ---------- TTS loop ----------
    def _tts_loop(self):
        while not self.stop_event.is_set():
            try:
                sentence = self.sentence_q.get(timeout=0.5)
            except Exception:
                continue

            if not is_speakable(sentence) or self.interrupt_flag.is_set():
                continue

            self._send_json({"type": "status", "state": "speaking"})
            self.eva_speaking.set()

            if not self.sarvam:
                # No TTS key configured - still "speak" via text so the
                # widget UI shows the reply, just without audio.
                self.eva_speaking.clear()
                if self.sentence_q.empty() and not self.interrupt_flag.is_set():
                    self._send_json({"type": "status", "state": "listening"})
                    self.turn_active = False
                continue

            leftover = b""
            try:
                for chunk in self.sarvam.text_to_speech.convert_stream(
                    text=sentence,
                    language_code="en-IN",
                    speaker=self.cfg["VOICE_TTS_SPEAKER"],
                    model=self.cfg["VOICE_TTS_MODEL"],
                    output_audio_codec="linear16",
                    speech_sample_rate=self.cfg["VOICE_TTS_SAMPLE_RATE"],
                    pace=self.cfg["VOICE_TTS_PACE"],
                ):
                    if self.interrupt_flag.is_set():
                        break
                    if not chunk:
                        continue
                    data = leftover + chunk
                    if len(data) % 2 != 0:
                        leftover = data[-1:]
                        data = data[:-1]
                    else:
                        leftover = b""
                    if data:
                        self._send_audio(data)
            except Exception as e:
                log("TTS", f"ERROR: {e}")

            self.eva_speaking.clear()

            if self.sentence_q.empty() and not self.interrupt_flag.is_set():
                self._send_json({"type": "status", "state": "listening"})
                self.turn_active = False