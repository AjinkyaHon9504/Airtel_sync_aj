"""Optional Gemini layer. Best-effort only: on no key, error, timeout or unsafe output the
caller keeps the deterministic result. Identifiers are redacted before text leaves the server.

Guardrails
  * extract(): returns only whitelisted profile fields, validated by type and range.
  * phrase(): every number in the model's reply must already appear in the source text,
    otherwise the reply is discarded (the model can't invent prices or quantities).
"""
from __future__ import annotations

import json
import os
import re

import httpx

from .nlu import redact

KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
STATS = {"calls": 0, "ok": 0, "fallbacks": 0}
LANG_NAMES = {"hi": "Hindi (Devanagari)", "hinglish": "Hinglish (Hindi in Roman script)", "mr": "Marathi", "ta": "Tamil",
              "te": "Telugu", "bn": "Bengali", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "en": "English"}


def enabled() -> bool:
    return bool(KEY)


def _call(prompt: str, json_mode: bool = False, timeout: float = 8.0) -> str | None:
    if not KEY:
        return None
    STATS["calls"] += 1
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, **({"responseMimeType": "application/json"} if json_mode else {})}}
    try:
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                       params={"key": KEY}, json=body, timeout=timeout)
        r.raise_for_status()
        out = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        STATS["ok"] += 1
        return out
    except Exception:
        STATS["fallbacks"] += 1
        return None


FIELDS = {"business_type": str, "segment": str, "city": str, "employees": int, "sites": int, "has_gst": bool,
          "needs": list, "removed_needs": list}
NEED_NAMES = ["payments", "whatsapp", "sms", "email", "cloud_backup", "failover", "cctv", "security", "firewall",
              "guest_wifi", "website", "static_ip", "telephony", "tollfree", "sdwan", "iot", "fleet", "sim",
              "sim_plus", "leased_line", "fibre", "fast_internet", "gigabit", "5g"]


def extract(text: str, known: dict) -> dict:
    """Fill gaps the rules missed. Returns {} when disabled or unsure."""
    if not KEY:
        return {}
    safe, _ = redact(text)
    prompt = (
        "Extract facts about a small Indian business from the owner's message (any Indian language or Hinglish).\n"
        f"Already known: {json.dumps(known, ensure_ascii=False)}\n"
        f"Message: \"{safe}\"\n"
        "Return JSON with only the keys you are confident about: business_type (English, short), "
        "segment (one of micro, prof, multi, mfg), city (English name), employees (int), sites (int), "
        f"has_gst (bool), needs (list from {NEED_NAMES}), removed_needs (same list, things they said they do NOT want). "
        "Never guess. Return {} if nothing is stated.")
    raw = _call(prompt, json_mode=True)
    try:
        d = json.loads(raw) if raw else {}
    except Exception:
        return {}
    out = {}
    for k, typ in FIELDS.items():
        if k in d and isinstance(d[k], typ):
            out[k] = d[k]
    if out.get("segment") not in (None, "micro", "prof", "multi", "mfg"):
        out.pop("segment")
    for k in ("employees", "sites"):
        if k in out and not (1 <= out[k] <= 5000):
            out.pop(k)
    for k in ("needs", "removed_needs"):
        if k in out:
            out[k] = [n for n in out[k] if n in NEED_NAMES]
    return out


def _numbers(s: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", s)}


def phrase(text: str, lang: str) -> str | None:
    """Translate / smooth a reply into the owner's language without changing any fact."""
    if not KEY or lang == "en":
        return None
    prompt = (f"Rewrite this message for a small-business owner in {LANG_NAMES.get(lang, lang)}. Keep it short and warm. "
              "Keep every number, ₹ amount, product name and **bold** marker exactly as given. Add no new facts, "
              f"prices or promises.\n\nMessage:\n{text}")
    out = _call(prompt)
    if not out:
        return None
    if not _numbers(out) <= _numbers(text):  # guard: no invented figures
        STATS["fallbacks"] += 1
        return None
    return out.strip()


def answer(question: str, facts: str, lang: str) -> str | None:
    if not KEY:
        return None
    safe, _ = redact(question)
    prompt = (f"You are the Accel Business onboarding assistant for small businesses. Answer in {LANG_NAMES.get(lang, 'English')}, "
              "in at most 3 short sentences, using ONLY these facts. If the facts don't cover it, say you'll connect them "
              f"with an advisor. Never invent prices, discounts or promises.\nFacts:\n{facts}\nQuestion: {safe}")
    out = _call(prompt)
    if out and _numbers(out) <= _numbers(facts + question):
        return out.strip()
    return None
