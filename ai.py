"""AI key: grab the selected text, ask Claude, paste the result back."""
from __future__ import annotations

import json
import time
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# mode: (name, instruction, paste back over the selection?)
MODES = {
    "translate_en": ("Translate to English", "Translate the text into English.", True),
    "translate_pl": ("Translate to Polish", "Translate the text into Polish.", True),
    "translate_ar": ("Translate to Arabic", "Translate the text into Arabic.", True),
    "fix": ("Fix grammar", "Fix grammar, spelling and flow. Keep the meaning, language and tone.", True),
    "formal": ("Make it professional", "Rewrite the text in a clear, polite, professional tone. Keep the same language.", True),
    "shorter": ("Make it shorter", "Rewrite the text to be about half as long. Keep the key points and the same language.", True),
    "summary": ("Summarize", "Summarize the text in 3 short bullet points.", False),
    "explain": ("Explain simply", "Explain the text in simple words in 2 or 3 sentences.", False),
    "reply": ("Draft a reply", "Write a short, friendly reply to this message. Same language as the message.", False),
    "custom": ("Custom prompt", "", True),
}
RULE = "Reply with only the result. No intro, no quotes, no notes."


def _clip():
    import pyperclip
    return pyperclip


def grab_selection(kb, Key) -> tuple[str, str]:
    """Copy the selected text. Returns (text, previous clipboard)."""
    pc = _clip()
    try:
        before = pc.paste()
    except Exception:
        before = ""
    pc.copy("")
    with kb.pressed(Key.ctrl):
        kb.press("c"); kb.release("c")
    for _ in range(12):
        time.sleep(0.05)
        try:
            t = pc.paste()
        except Exception:
            t = ""
        if t:
            return t, before
    return "", before


def paste(text: str, kb, Key):
    _clip().copy(text)
    time.sleep(0.05)
    with kb.pressed(Key.ctrl):
        kb.press("v"); kb.release("v")


def ask(api_key: str, model: str, mode: str, text: str, custom: str = "") -> str:
    name, instr, _ = MODES.get(mode, MODES["fix"])
    system = f"{custom or instr} {RULE}"
    body = {"model": model or DEFAULT_MODEL, "max_tokens": 1500, "system": system,
            "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"Claude API error {e.code}: {msg}") from None
    return "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text").strip()
