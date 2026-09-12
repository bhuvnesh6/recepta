"""
LLM provider abstraction.

Business logic never talks to Groq/Mistral/OpenRouter directly - it calls
llm.generate(...) / llm.stream(...). Swapping providers means editing this
file only.
"""
import json
import requests
from flask import current_app


class LLMProvider:
    def generate(self, messages, tools=None, temperature=0.4, max_tokens=800):
        raise NotImplementedError

    def stream(self, messages, tools=None, temperature=0.4, max_tokens=800):
        raise NotImplementedError


class GroqProvider(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
    MODEL = "llama-3.3-70b-versatile"

    def __init__(self, api_key):
        self.api_key = api_key

    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def generate(self, messages, tools=None, temperature=0.4, max_tokens=800):
        if not self.api_key:
            return _stub_response(messages)
        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        resp = requests.post(self.BASE_URL, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]["message"]
        return {
            "content": choice.get("content", ""),
            "tool_calls": choice.get("tool_calls", []),
        }

    def stream(self, messages, tools=None, temperature=0.4, max_tokens=800):
        """Streaming generator - yields plain text deltas as they arrive
        (already parsed out of the provider's SSE `data:` frames), not raw
        JSON. Falls back to one-shot if no key configured."""
        if not self.api_key:
            yield _stub_response(messages)["content"]
            return
        payload = {
            "model": self.MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with requests.post(self.BASE_URL, headers=self._headers(), json=payload,
                            stream=True, timeout=30) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if not text.startswith("data: "):
                    continue
                data = text[6:]
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue


class MistralProvider(LLMProvider):
    BASE_URL = "https://api.mistral.ai/v1/chat/completions"
    MODEL = "mistral-large-latest"

    def __init__(self, api_key):
        self.api_key = api_key

    def generate(self, messages, tools=None, temperature=0.4, max_tokens=800):
        if not self.api_key:
            return _stub_response(messages)
        payload = {"model": self.MODEL, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
        resp = requests.post(
            self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]
        return {"content": choice.get("content", ""), "tool_calls": choice.get("tool_calls", [])}

    def stream(self, messages, tools=None, temperature=0.4, max_tokens=800):
        yield self.generate(messages, tools, temperature, max_tokens)["content"]


class OpenRouterProvider(LLMProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "meta-llama/llama-3.3-70b-instruct"

    def __init__(self, api_key):
        self.api_key = api_key

    def generate(self, messages, tools=None, temperature=0.4, max_tokens=800):
        if not self.api_key:
            return _stub_response(messages)
        payload = {"model": self.MODEL, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
        resp = requests.post(
            self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]["message"]
        return {"content": choice.get("content", ""), "tool_calls": choice.get("tool_calls", [])}

    def stream(self, messages, tools=None, temperature=0.4, max_tokens=800):
        yield self.generate(messages, tools, temperature, max_tokens)["content"]


def _stub_response(messages):
    """No API key configured yet - keeps the app fully runnable/demoable."""
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return {
        "content": (
            "(LLM provider not configured yet - add GROQ_API_KEY/MISTRAL_API_KEY/"
            "OPENROUTER_API_KEY in .env) I heard: " + last_user[:200]
        ),
        "tool_calls": [],
    }


def get_llm_provider() -> LLMProvider:
    provider = current_app.config.get("LLM_PROVIDER", "groq")
    if provider == "mistral":
        return MistralProvider(current_app.config.get("MISTRAL_API_KEY", ""))
    if provider == "openrouter":
        return OpenRouterProvider(current_app.config.get("OPENROUTER_API_KEY", ""))
    return GroqProvider(current_app.config.get("GROQ_API_KEY", ""))