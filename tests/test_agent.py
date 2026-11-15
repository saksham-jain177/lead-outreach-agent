"""Unit tests — all external calls (search, LLM, gog subprocess) are mocked."""
import datetime as dt
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent
import enrich
import outreach
import pitch
import sheets


# ---------- command parsing ----------

def test_parse_command():
    assert agent.parse_command("Find event leads for Zomato in Gurgaon") == ("Zomato", "Gurgaon")
    assert agent.parse_command("find event leads for Zoho in Chennai") == ("Zoho", "Chennai")
    assert agent.parse_command("hello world") is None
    assert agent.parse_command("Find event leads for Acme Corp in New Delhi") == ("Acme Corp", "New Delhi")


# ---------- search (mocked) ----------

def test_search_web_uses_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = {"n": 0}

    def fake_ddg(query, max_results=6):
        calls["n"] += 1
        return [{"title": "t", "body": "b", "href": "h"}]

    monkeypatch.setattr(enrich, "_ddg_search", fake_ddg)
    r1 = enrich.search_web("query one")
    r2 = enrich.search_web("query one")
    assert r1 == r2 == [{"title": "t", "body": "b", "href": "h"}]
    assert calls["n"] == 1  # second call served from cache.json


def test_search_web_falls_back_to_tavily(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom(q, max_results=6):
        raise RuntimeError("ddg down")

    monkeypatch.setattr(enrich, "_ddg_search", boom)
    monkeypatch.setattr(enrich, "_tavily_search", lambda q, max_results=6: [
        {"title": "tv", "body": "tv-body", "href": "https://x"}])
    assert enrich.search_web("q") == [{"title": "tv", "body": "tv-body", "href": "https://x"}]


# ---------- lead extraction ----------

def test_extract_lead_finds_email_and_linkedin():
    results = [
        {"title": "Zomato leadership", "body": "Deepinder Goyal — Founder & CEO of Zomato, "
         "reach him at deepinder@zomato.com or https://linkedin.com/in/deepindergoyal", "href": ""},
    ]
    lead = enrich.extract_lead("Zomato", "Gurgaon", results)
    assert lead["name"] == "Deepinder Goyal"
    assert lead["email"] == "deepinder@zomato.com"
    assert "linkedin.com/in/deepindergoyal" in lead["linkedin"]


def test_extract_lead_fallback_row_when_no_contact():
    lead = enrich.extract_lead("UnknownCorp", "UnknownCity", [
        {"title": "UnknownCorp homepage", "body": "We make widgets.", "href": ""}])
    assert lead["email"] is None
    assert lead["name"] == "Unknown"


def test_extract_lead_ignores_junk_emails():
    results = [{"title": "img", "body": "contact us at noreply@zomato.com or see logo@2x.png", "href": ""}]
    lead = enrich.extract_lead("Zomato", "Gurgaon", results)
    assert lead["email"] is None


def test_email_present_in_text_rejects_fragments():
    # 'l@gmail.com' is a truncation of 'angel@gmail.com' — must NOT count as present
    assert enrich.email_present_in_text("l@gmail.com", "mail angel@gmail.com now") is False
    assert enrich.email_present_in_text("angel@gmail.com", "mail angel@gmail.com now") is True
    assert enrich.email_present_in_text("a@b.co", "nothing here") is False


def test_plausible_email_rejects_short_local_parts():
    assert enrich.plausible_email("l@gmail.com") is False
    assert enrich.plausible_email("ab@x.co") is False
    assert enrich.plausible_email("deepinder@zomato.com") is True
    assert enrich.plausible_email("not-an-email") is False


# ---------- pitch (mocked LLM, strict contract) ----------

def test_write_pitch_three_lines_from_llm(monkeypatch):
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300:
                        "\nLine one about Zomato.\nLine two about vetted crews.\nLine three CTA.")
    out = pitch.write_pitch("Zomato", "Gurgaon", {"name": "Deepinder Goyal", "role": "Founder & CEO", "event_signals": []})
    assert len(out.splitlines()) == 3


def test_write_pitch_retries_on_bad_shape_then_succeeds(monkeypatch):
    calls = {"n": 0}
    def fake_chat(prompt, system=None, temperature=0.2, max_tokens=300):
        calls["n"] += 1
        return "only one line" if calls["n"] == 1 else "\n".join(
            ["a", "b", "c"])
    monkeypatch.setattr("llm.chat", fake_chat)
    out = pitch.write_pitch("Zomato", "Gurgaon", {"name": "X", "role": "CEO", "event_signals": []})
    assert calls["n"] == 2 and len(out.splitlines()) == 3


def test_write_pitch_fallback_when_llm_fails(monkeypatch):
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300: None)
    out = pitch.write_pitch("Zomato", "Gurgaon", {"name": "Deepinder Goyal", "role": "Founder & CEO", "event_signals": []})
    assert len(out.splitlines()) == 3
    assert "Zomato" in out


def test_pitch_rejects_overlong_lines():
    long_line = "x" * 130
    ok, _ = pitch._valid_pitch(f"{long_line}\nshort\nshort")
    assert ok is False


# ---------- strict-JSON lead extraction contract ----------

def _lead_json(**overrides):
    base = {"name": "Deepinder Goyal", "role": "Founder & CEO", "company": "Zomato",
            "city": "Gurgaon", "contact_email": None, "linkedin_url": None, "confidence": 0.9}
    base.update(overrides)
    return base


def test_llm_extract_lead_valid_json(monkeypatch):
    import json as _json
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300:
                        _json.dumps(_lead_json(contact_email="deepinder@zomato.com")))
    results = [{"title": "t", "body": "reach Deepinder at deepinder@zomato.com", "href": "h"}]
    out = enrich.llm_extract_lead("Zomato", "Gurgaon", results)
    assert out["contact_email"] == "deepinder@zomato.com"
    assert out["confidence"] == 0.9


def test_llm_extract_lead_retries_once_on_bad_json(monkeypatch):
    import json as _json
    calls = {"n": 0}
    def fake_chat(prompt, system=None, temperature=0.2, max_tokens=300):
        calls["n"] += 1
        return "not json at all" if calls["n"] == 1 else _json.dumps(_lead_json())
    monkeypatch.setattr("llm.chat", fake_chat)
    out = enrich.llm_extract_lead("Zomato", "Gurgaon", [{"title": "t", "body": "b", "href": ""}])
    assert calls["n"] == 2 and out["name"] == "Deepinder Goyal"


def test_llm_extract_lead_gives_up_gracefully(monkeypatch):
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300: '{"name": "x"}')  # missing keys
    assert enrich.llm_extract_lead("Zomato", "Gurgaon", [{"title": "t", "body": "b", "href": ""}]) is None


def test_llm_extract_lead_rejects_fabricated_email(monkeypatch):
    # Model disobeys the anti-hallucination rule and pattern-generates an email
    # that appears in NO snippet — the code must null it out.
    import json as _json
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300:
                        _json.dumps(_lead_json(contact_email="founder@zomato.com")))
    results = [{"title": "Zomato", "body": "Deepinder Goyal is CEO", "href": ""}]
    out = enrich.llm_extract_lead("Zomato", "Gurgaon", results)
    assert out is not None
    assert out["contact_email"] is None  # fabricated email nulled
    assert out["name"] == "Deepinder Goyal"  # name kept (present in snippets)


def test_llm_extract_lead_keeps_email_present_in_snippets(monkeypatch):
    import json as _json
    monkeypatch.setattr("llm.chat", lambda p, system=None, temperature=0.2, max_tokens=300:
                        _json.dumps(_lead_json(contact_email="deepinder@zomato.com")))
    results = [{"title": "Zomato", "body": "contact deepinder@zomato.com", "href": ""}]
    out = enrich.llm_extract_lead("Zomato", "Gurgaon", results)
    assert out["contact_email"] == "deepinder@zomato.com"


def test_enrich_uses_llm_result_and_respects_nulls(monkeypatch, tmp_path):
    import json as _json
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(enrich, "search_web", lambda q, max_results=6: [
        {"title": "Zomato leadership", "body": "Deepinder Goyal — Founder & CEO of Zomato in Gurgaon", "href": ""}])
    monkeypatch.setattr(enrich.llm, "chat", lambda p, system=None, temperature=0.2, max_tokens=300:
                        _json.dumps(_lead_json()))  # email null — nothing in snippets
    lead = enrich.enrich("Zomato", "Gurgaon")
    assert lead["name"] == "Deepinder Goyal"
    assert lead["email"] is None  # null respected — no fabrication
    assert "confidence" in lead


# ---------- llm defensive parsing ----------

def test_llm_extract_text_shapes():
    from llm import _extract_text
    assert _extract_text({"choices": [{"message": {"content": "hello"}}]}) == "hello"
    assert _extract_text({"choices": [{"message": {"content": None, "reasoning": "thoughts"}}]}) == "thoughts"
    think_open, think_close = "<" + "think" + ">", "</" + "think" + ">"
    leaky = think_open + "chain of thought" + think_close + "final"
    assert _extract_text({"choices": [{"message": {"content": leaky}}]}) == "final"
    assert _extract_text({}) == ""


def test_llm_chat_skips_429(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "model_chain", lambda: ["m1", "m2"])

    class R:
        def __init__(self, code, data):
            self.status_code, self._d = code, data
        def json(self):
            return self._d

    ok = {"choices": [{"message": {"content": "fine"}}]}
    responses = [R(429, {}), R(429, {}), R(200, ok)]
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.chat("hi") == "fine"


# ---------- sheets (mocked subprocess) ----------

def test_append_row_builds_correct_gog_call():
    values = ["2026-11-15", "Zomato", "Gurgaon", "Enriched", "Deepinder Goyal", "Founder & CEO",
              "deepinder@zomato.com", "https://linkedin.com/in/x", "line1, with comma / line2", "NO", ""]
    captured = {}

    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(sheets.subprocess, "run", side_effect=fake_run), \
         mock.patch.dict(os.environ, {"GOG_EXE": "gog.exe", "GOOGLE_SHEET_ID": "SHEETID", "GOG_ACCOUNT": ""}):
        assert sheets.append_row(values) is True
    cmd = captured["cmd"]
    assert "sheets" in cmd and "append" in cmd and "SHEETID" in cmd
    assert "--values-json" in cmd
    import json as _json
    payload = _json.loads(cmd[cmd.index("--values-json") + 1])
    assert payload[0][1] == "Zomato" and payload[0][4] == "Deepinder Goyal"
    assert "\n" not in payload[0][8]  # newlines sanitized to single-line cells


def test_append_row_rejects_wrong_shape():
    assert sheets.append_row(["only", "four"]) is False


# ---------- outreach ----------

def test_outreach_email_never_targets_real_lead():
    lead = {"name": "Deepinder Goyal", "role": "Founder & CEO", "email": "deepinder@zomato.com",
            "linkedin": ""}
    subject, body = outreach.outreach_email(lead, "Zomato", "Gurgaon", "p1\np2\np3")
    assert "DEMO" in subject
    assert "NOT to the real lead" in body
    assert "deepinder@zomato.com" in body  # quoted in body only


def test_process_followups_sends_due_rows(tmp_path, monkeypatch):
    today = dt.date(2026, 11, 15)
    rows = [[
        "2026-11-12", "Zomato", "Gurgaon", "Enriched", "Deepinder Goyal", "Founder & CEO",
        "deepinder@zomato.com", "", "p1 / p2 / p3", "YES", "2026-11-14",  # due
    ], [
        "2026-11-12", "Zoho", "Chennai", "Enriched", "Sridhar Vembu", "Founder & CEO",
        "", "", "p1 / p2 / p3", "YES", "2026-11-20",  # not due
    ]]
    sent = []

    def fake_gog(args, timeout=60):
        sent.append(args)
        return mock.Mock(returncode=0, stdout="id: 123", stderr="")

    monkeypatch.setattr(outreach, "_gog", fake_gog)
    monkeypatch.setattr(outreach.sheets, "update_row", lambda *a, **k: True)
    monkeypatch.setattr(outreach.sheets, "find_rows", lambda: [(2, rows[0]), (3, rows[1])])
    actions = outreach.process_followups(today=today.isoformat())
    assert len(actions) == 1 and actions[0]["company"] == "Zomato" and actions[0]["sent"] is True
    assert any("--subject" in " ".join(a) for a in sent)


def test_followup_date_is_future():
    assert outreach.followup_date() > dt.date.today().isoformat()


# ---------- telegram authorization ----------

def test_resolve_allowed_user_from_env(monkeypatch):
    import telegram_bot
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "897442810")
    assert telegram_bot._resolve_allowed_user() == 897442810
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    assert telegram_bot._resolve_allowed_user() is None
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-a-number")
    assert telegram_bot._resolve_allowed_user() is None


def test_listener_ignores_unauthorized_and_answers_authorized(monkeypatch):
    import telegram_bot

    class FakeMsg(dict):
        pass

    def make_update(uid, chat_id, text):
        return {"update_id": uid, "message": {"chat": {"id": chat_id}, "text": text}}

    updates = [
        make_update(1, 999999, "Find event leads for Zomato in Gurgaon"),   # unauthorized
        make_update(2, 897442810, "Find event leads for Zoho in Chennai"),  # authorized
        make_update(3, 897442810, "hello"),                                 # authorized, bad command
    ]
    sent = []
    ran = []

    def fake_api(token, method, payload=None, timeout=60):
        if method == "getUpdates":
            if not updates:
                raise KeyboardInterrupt  # stop the poll loop when drained
            batch, updates[:] = updates[:1], updates[1:]
            return {"ok": True, "result": batch}
        if method == "sendMessage":
            sent.append(payload)
        return {"ok": True}

    monkeypatch.setattr(telegram_bot, "_api", fake_api)
    monkeypatch.setattr(telegram_bot.agent, "run_pipeline",
                        lambda *a, **k: ran.append(a) or {"lead": {"name": "X", "role": "CEO"},
                                                          "pitch": "p", "sheet": "appended",
                                                          "outreach": "sent"})

    with pytest.raises(KeyboardInterrupt):
        telegram_bot.poll_forever(allowed_user_id=897442810)

    assert len(ran) == 1 and ran[0] == ("Zoho", "Chennai")  # only authorized chat ran
    acks = [s for s in sent if s["text"] == "On it — running enrichment..."]
    assert len(acks) == 1 and acks[0]["chat_id"] == 897442810
    help_msgs = [s for s in sent if "Find event leads for" in s["text"] and "Send:" in s["text"]]
    assert len(help_msgs) == 1  # only the authorized bad-command got the help reply
