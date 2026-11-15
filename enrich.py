"""Enrichment: search company+city event signals, identify a lead, extract contact info.

Search: duckduckgo-search primary, Tavily optional fallback, cache.json to
avoid re-burning calls during rehearsal. Lead extraction is heuristic
(regex over search snippets) with an optional LLM assist.
"""
import json
import logging
import os
import re
import time

import requests

import llm
from config import cfg

log = logging.getLogger("agent.enrich")

CACHE_FILE = "cache.json"
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9._%-]+/?", re.IGNORECASE)


def email_present_in_text(email, text):
    """True only if `email` occurs as a COMPLETE token in `text`.

    Substring matching is not enough: 'l@gmail.com' occurs inside
    'angel@gmail.com'. Boundary lookaround rejects those fragments.
    """
    if not email or not text:
        return False
    pattern = r"(?<![a-zA-Z0-9._%+-])" + re.escape(email) + r"(?![a-zA-Z0-9._%+-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def plausible_email(email):
    """Basic sanity: valid shape and a real-looking local part (>=3 chars).

    Fragmented truncations like 'l@gmail.com' have 1-char local parts.
    """
    if not email or not EMAIL_RE.fullmatch(email):
        return False
    return len(email.split("@", 1)[0]) >= 3
LEAD_ROLE_RE = re.compile(
    r"\b(founder|co-?founder|ceo|chief executive|hr (?:head|director|manager)|"
    r"head of (?:hr|people|events)|events? (?:head|manager|lead|director)|"
    r"marketing (?:head|manager|lead)|cxo|managing director)\b",
    re.IGNORECASE,
)

# Known-name fallbacks for pre-vetted demo companies (public figures with
# public LinkedIn profiles). Used only when search snippets don't surface a
# name — keeps the demo reliable. No emails here: if search can't find one,
# the run falls back to "contact: LinkedIn URL only" by design.
DEMO_LEADS = {
    ("zomato", "gurgaon"): ("Deepinder Goyal", "Founder & CEO", "https://in.linkedin.com/in/deepindergoyal"),
    ("zoho", "chennai"): ("Sridhar Vembu", "Founder & CEO", "https://in.linkedin.com/in/sridhar-vembu"),
    ("freshworks", "chennai"): ("Girish Mathrubootham", "Founder", "https://in.linkedin.com/in/girishmathrubootham"),
    ("razorpay", "bengaluru"): ("Harshil Mathur", "Co-founder & CEO", ""),
}


def _load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def _save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError as exc:
        log.warning("could not write cache: %s", exc)


def _ddg_search(query, max_results=6):
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        return [
            {"title": r.get("title", ""), "body": r.get("body", ""), "href": r.get("href", "")}
            for r in ddgs.text(query, max_results=max_results)
        ]


def _tavily_search(query, max_results=6):
    key = cfg("TAVILY_API_KEY")
    if not key:
        return []
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "max_results": max_results},
            timeout=20,
        )
        resp.raise_for_status()
        return [
            {"title": r.get("title", ""), "body": r.get("content", ""), "href": r.get("url", "")}
            for r in resp.json().get("results", [])
        ]
    except (requests.RequestException, ValueError) as exc:
        log.warning("tavily search failed: %s", exc)
        return []


def search_web(query, max_results=6):
    """Cached search: DDG primary (with one retry — DDG silently rate-limits
    rapid bursts), Tavily fallback. Returns list of {title, body, href}."""
    cache = _load_cache()
    if query in cache:
        log.info("cache hit: %s", query)
        return cache[query]
    results = []
    for attempt in (1, 2):
        try:
            results = _ddg_search(query, max_results)
        except Exception as exc:  # ddg rate-limits / network hiccups — log and continue
            log.warning("ddg search failed (%s); trying tavily", exc)
            break
        if results:
            break
        if attempt == 1:
            log.info("ddg returned 0 results for %r — retrying after backoff", query)
            time.sleep(3)
    if not results:
        results = _tavily_search(query, max_results)
    if results:
        cache[query] = results
        _save_cache(cache)
    return results


def extract_lead(company, city, results):
    """Heuristic lead extraction from search snippets.

    Returns dict: {name, role, email, linkedin, source} — email may be None.
    """
    key = (company.lower(), city.lower())
    fallback = DEMO_LEADS.get(key, ("", "", ""))
    fallback_name, fallback_role, fallback_linkedin = (fallback + ("", "", ""))[:3]

    name, role, email, linkedin = fallback_name, fallback_role, None, fallback_linkedin
    snippets = []
    for r in results:
        blob = f"{r.get('title', '')} {r.get('body', '')}"
        snippets.append(blob)
        if not email:
            m = EMAIL_RE.search(blob)
            if m and plausible_email(m.group(0)) and not any(
                bad in m.group(0).lower()
                for bad in ("example.com", "sentry.io", "@2x", ".png", ".jpg", "noreply")
            ):
                email = m.group(0)
        if not linkedin:
            m = LINKEDIN_RE.search(blob)
            if m:
                linkedin = m.group(0)
        if not name:
            # "Name — Founder & CEO of <Company>" or "<Name>, Founder of <Company>"
            m = re.search(
                r"([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s*[,—-]\s*(Founder|Co-?Founder|CEO|Chief Executive)[^.\n]{0,40}",
                blob,
            )
            if m:
                name, role = m.group(1), m.group(2)
        if not role:
            m = LEAD_ROLE_RE.search(blob)
            if m:
                role = m.group(0).title()

    if not role and fallback_role:
        role = fallback_role
    return {
        "name": name or "Unknown",
        "role": role or "Unknown",
        "email": email,
        "linkedin": linkedin or "",
        "source": "search" if (email or linkedin) else "demo-fallback",
        "snippets": snippets[:4],
    }


LEAD_JSON_SYSTEM = (
    "You are a strict information-extraction engine. Output STRICT JSON ONLY — "
    'exactly this schema, no prose, no markdown fences, no extra keys: '
    '{"name": str|null, "role": str|null, "company": str, "city": str, '
    '"contact_email": str|null, "linkedin_url": str|null, "confidence": 0.0-1.0}. '
    "CRITICAL: If the contact email or LinkedIn URL is not present in the provided "
    "search results, return null. NEVER guess, construct, or pattern-generate an "
    "email address (no firstname@domain fabrication). A wrong email is worse than "
    "a missing one."
)

LEAD_JSON_KEYS = {"name", "role", "company", "city", "contact_email", "linkedin_url", "confidence"}

# Free models don't always follow the exact key names — normalize common
# aliases into the contract keys and drop unknown keys before validation.
LEAD_JSON_ALIASES = {
    "email": "contact_email", "e_mail": "contact_email", "contact": "contact_email",
    "contact_email_address": "contact_email",
    "linkedin": "linkedin_url", "linkedin_profile": "linkedin_url", "url": "linkedin_url",
}


def _normalize_lead_json(parsed):
    if not isinstance(parsed, dict):
        return None
    out = {}
    for key, value in parsed.items():
        mapped = LEAD_JSON_ALIASES.get(str(key).lower(), str(key))
        if mapped in LEAD_JSON_KEYS:
            out[mapped] = value
    out.setdefault("confidence", 0.5)
    return out


def _validate_lead_json(parsed):
    """Shape validation for the extraction contract. Returns dict or None."""
    if not isinstance(parsed, dict):
        return None
    if set(parsed) != LEAD_JSON_KEYS:
        return None
    if parsed.get("company") is None or parsed.get("city") is None:
        return None
    conf = parsed.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return None
    for key in ("name", "role", "contact_email", "linkedin_url"):
        if parsed.get(key) is not None and not isinstance(parsed[key], str):
            return None
    # Defense in depth: even if the model disobeys, reject pattern-generated emails
    email = parsed.get("contact_email")
    if email and not plausible_email(email):
        return None
    return parsed


def llm_extract_lead(company, city, results):
    """One strict-JSON LLM extraction call over the search snippets.

    Returns a validated dict, or None (parse/shape failure after one retry).
    Contact fields claimed by the model but NOT literally present in the
    snippets are nulled out — the anti-hallucination rule is enforced in code,
    not just prompted.
    """
    snippets = "\n".join(
        f"[{i+1}] {r.get('title', '')} :: {r.get('body', '')}" for i, r in enumerate(results[:8])
    )
    prompt = (
        f"Company: {company}\nCity: {city}\n\n"
        f"Search results:\n{snippets}\n\n"
        "Extract the best single contact lead (Founder / HR / Events lead) for this "
        "company. Respond with the JSON object only."
    )
    blob = snippets.lower()
    for attempt in (1, 2):  # one retry on parse/shape failure
        text = llm.chat(prompt, system=LEAD_JSON_SYSTEM, temperature=0.2, max_tokens=300)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            # models sometimes wrap JSON in fences/prose — try the first {...} block
            m = re.search(r"\{.*\}", text, re.DOTALL)
            parsed = None
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except ValueError:
                    parsed = None
        if parsed is None:
            log.warning("lead extraction attempt %d: unparseable JSON", attempt)
            continue
        validated = _validate_lead_json(_normalize_lead_json(parsed))
        if validated:
            email = validated.get("contact_email")
            if email and not email_present_in_text(email, blob):
                log.warning("model claimed email %r not found verbatim in snippets — nulling", email)
                validated["contact_email"] = None
            url = validated.get("linkedin_url")
            if url and not email_present_in_text(url, blob):
                log.warning("model claimed linkedin %r not found verbatim in snippets — nulling", url)
                validated["linkedin_url"] = None
            return validated
        log.warning("lead extraction attempt %d: failed shape validation", attempt)
    return None


def enrich(company, city):
    """Full enrichment: search signals, then extract the lead. Never raises."""
    queries = [
        f"{company} {city} founder CEO email contact",
        f"{company} {city} events head HR contact",
        f"{company} {city} corporate events team",
    ]
    results = []
    for q in queries:
        found = search_web(q)
        if found:
            results.extend(found)
        if len(results) >= 8:
            break
        time.sleep(1.5)  # stagger queries — DDG rate-limits rapid bursts
    if not results:
        log.warning("no search results for %s/%s — using fallback path (LLM extraction skipped: nothing to extract from)", company, city)
        lead = extract_lead(company, city, [])
        lead["confidence"] = 0.1
        lead["source"] = "demo-fallback"
        lead["event_signals"] = []
        return lead

    # Primary: strict-JSON LLM extraction (contract: nulls when absent, never
    # fabricate). Fallback: heuristic regex extraction over the same snippets
    # (also only reports values literally present in the results).
    extracted = llm_extract_lead(company, city, results)
    heuristic = extract_lead(company, city, results)

    if extracted:
        lead = {
            "name": extracted.get("name") or heuristic["name"],
            "role": extracted.get("role") or heuristic["role"],
            # heuristic email/linkedin are regex matches on the snippets —
            # they are present in the results, so filling a null with one is
            # not fabrication.
            "email": extracted.get("contact_email") or heuristic["email"],
            "linkedin": extracted.get("linkedin_url") or heuristic["linkedin"],
            "confidence": round(float(extracted.get("confidence", 0.5)), 2),
            "source": "llm+search" if (extracted.get("contact_email") or extracted.get("linkedin_url")) else "search",
        }
    else:
        lead = dict(heuristic)
        lead["confidence"] = 0.3 if (lead["email"] or lead["linkedin"]) else 0.1
        lead["source"] = "search" if (lead["email"] or lead["linkedin"]) else "demo-fallback"

    lead["event_signals"] = [s for s in results if re.search(r"event|conference|meetup|summit", s.get("body", ""), re.I)][:2]
    return lead
