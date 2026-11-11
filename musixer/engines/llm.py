"""Text generation via Ollama, any OpenAI-compatible endpoint, or None (offline fallback)."""
import json
import re

import httpx

from ..config import load_settings


class LLMUnavailable(RuntimeError):
    pass


def _ollama_models(url):
    try:
        r = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=2)
        return [m["name"] for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        return []


def resolve():
    """Return (provider, model) actually usable right now, or (None, None)."""
    s = load_settings()
    p = s.get("llm_provider", "auto")
    if p == "offline":
        return None, None
    if p == "openai" or (p == "auto" and s.get("openai_api_key")):
        if s.get("openai_base_url"):
            return "openai", s.get("openai_model")
    if p in ("ollama", "auto"):
        models = _ollama_models(s["ollama_url"])
        if models:
            want = s.get("ollama_model")
            return "ollama", want if want in models else models[0]
    return None, None


def status():
    s = load_settings()
    provider, model = resolve()
    return {
        "provider": provider or "offline",
        "model": model,
        "configured": s.get("llm_provider"),
        "ollama_models": _ollama_models(s["ollama_url"]),
    }


def chat(system, user, temperature=0.9, max_tokens=1200):
    s = load_settings()
    provider, model = resolve()
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    if provider == "ollama":
        r = httpx.post(
            f"{s['ollama_url'].rstrip('/')}/api/chat",
            json={"model": model, "messages": msgs, "stream": False,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
            timeout=300,
        )
        r.raise_for_status()
        return _strip_think(r.json()["message"]["content"])
    if provider == "openai":
        headers = {"Authorization": f"Bearer {s['openai_api_key']}"} if s.get("openai_api_key") else {}
        r = httpx.post(
            f"{s['openai_base_url'].rstrip('/')}/chat/completions",
            json={"model": model, "messages": msgs, "temperature": temperature, "max_tokens": max_tokens},
            headers=headers, timeout=300,
        )
        r.raise_for_status()
        return _strip_think(r.json()["choices"][0]["message"]["content"])
    raise LLMUnavailable("No LLM configured")


def _strip_think(text):
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def chat_json(system, user, temperature=0.9, max_tokens=1500):
    text = chat(system + "\nRespond with JSON only, no markdown fences.", user, temperature, max_tokens)
    return parse_json(text)


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        a, b = text.find(open_c), text.rfind(close_c)
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError:
                continue
    raise ValueError(f"Model did not return valid JSON: {text[:200]}")
