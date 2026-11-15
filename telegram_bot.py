"""Telegram trigger — thin wrapper over the core pipeline (agent.run_pipeline).

The CLI works without this module; Telegram is only enabled when
TELEGRAM_BOT_TOKEN is set. Long polling via the raw Bot API (no deps).
"""
import json
import logging
import urllib.request

import agent
from config import cfg

log = logging.getLogger("agent.telegram")

API = "https://api.telegram.org/bot{token}/{method}"


def _api(token, method, payload=None, timeout=60):
    req = urllib.request.Request(
        API.format(token=token, method=method),
        data=json.dumps(payload).encode() if payload else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _resolve_allowed_user():
    """Authorized user from env (TELEGRAM_CHAT_ID). None = accept any chat."""
    chat_id = cfg("TELEGRAM_CHAT_ID")
    try:
        return int(chat_id) if chat_id else None
    except ValueError:
        log.warning("TELEGRAM_CHAT_ID=%r is not an integer — ignoring", chat_id)
        return None


def poll_forever(allowed_user_id=None):
    """Long-poll updates; run the pipeline on matching commands.

    allowed_user_id: when set (default: TELEGRAM_CHAT_ID from .env), messages
    from any other chat are ignored — the operator is the only authorized user.
    """
    token = cfg("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set — Telegram trigger disabled. Use the CLI.")
        return
    if allowed_user_id is None:
        allowed_user_id = _resolve_allowed_user()
    offset = 0
    print("Telegram listener polling... (Ctrl+C to stop)"
          + (f" Authorized user: {allowed_user_id}" if allowed_user_id else " [no TELEGRAM_CHAT_ID — accepting any chat]"))
    while True:
        try:
            data = _api(token, "getUpdates", {"offset": offset, "timeout": 30}, timeout=40)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat_id = msg.get("chat", {}).get("id")
                if not text or (allowed_user_id and chat_id != allowed_user_id):
                    if text:
                        log.info("ignored message from unauthorized chat %s", chat_id)
                    continue
                parsed = agent.parse_command(text)
                if not parsed:
                    _api(token, "sendMessage", {
                        "chat_id": chat_id,
                        "text": 'Send: "Find event leads for <company> in <city>"',
                    })
                    continue
                _api(token, "sendMessage", {"chat_id": chat_id, "text": "On it — running enrichment..."})
                result = agent.run_pipeline(*parsed)
                summary = (
                    f"Lead: {result['lead']['name']} ({result['lead']['role']})\n"
                    f"Pitch:\n{result['pitch']}\n"
                    f"Sheet: {result['sheet']} | Outreach: {result['outreach']}"
                )
                _api(token, "sendMessage", {"chat_id": chat_id, "text": summary})
        except Exception as exc:
            log.warning("poll error: %s — retrying in 5s", exc)
            import time
            time.sleep(5)


if __name__ == "__main__":
    config.load_env()
    poll_forever()
