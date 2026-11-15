"""Pitch writer: ONE LLM call producing a fixed 3-line pitch."""
import logging

import llm

log = logging.getLogger("agent.pitch")

SYSTEM = (
    "You write outreach pitches for an event-industry marketplace that connects "
    "event hosts with vetted event planners, DJs, and crew. Output EXACTLY 3 lines "
    "— no preamble, no numbering, no markdown, no quotes. Each line under 120 "
    "characters. Use only facts present in the provided lead data. Do not invent "
    "company facts, metrics, or claims."
)

TEMPLATE = """Write a personalized 3-line outreach pitch.

Line 1: why we're reaching out to {lead_name} ({lead_role}) at {company} in {city} — reference one local event or growth signal.
Line 2: what we offer — vetted event planners, DJs, and crew for their events.
Line 3: a soft call-to-action (a 15-minute call this week).

Event context from research:
{event_context}

Keep each line under 25 words. Plain sentences, one per line."""


def _valid_pitch(text):
    """Contract check: exactly 3 non-empty lines, each <= 120 chars."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return len(lines) == 3 and all(len(ln) <= 120 for ln in lines), lines


def write_pitch(company, city, lead):
    """Return a 3-line pitch string. Falls back to a deterministic template on LLM failure."""
    event_context = "\n".join(
        f"- {s.get('title', '')}: {s.get('body', '')[:150]}"
        for s in (lead.get("event_signals") or [])[:2]
    ) or "(no specific event signals found — reference the company's growth in {city})".format(city=city)

    prompt = TEMPLATE.format(
        lead_name=lead.get("name", "there"),
        lead_role=lead.get("role", "the team"),
        company=company,
        city=city,
        event_context=event_context,
    )
    # One retry on contract failure (line count / length), per the output contract
    for attempt in (1, 2):
        text = llm.chat(prompt, system=SYSTEM, temperature=0.2, max_tokens=300)
        if not text:
            continue
        ok, lines = _valid_pitch(text)
        if ok:
            return "\n".join(lines)
        log.warning("pitch attempt %d failed validation (%d lines)", attempt, len(lines))

    log.warning("LLM pitch failed — using deterministic fallback")
    return (
        f"Hi {lead.get('name', 'there')}, noticed {company}'s event activity in {city} and thought of you.\n"
        "We connect event hosts with vetted planners, DJs, and crew — one marketplace, zero coordination overhead.\n"
        "Open to a quick 15-minute call this week to see if this fits your next event?"
    )
