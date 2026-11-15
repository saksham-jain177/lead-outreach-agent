# Lead Enrichment & Outreach Agent

A BDR lead-enrichment and outreach agent for an event-industry marketplace
(connecting event hosts with vetted planners, DJs, and crew). Given a company
and a city, it finds the right contact (Founder / HR / Events lead), writes a
tailored 3-line pitch, logs the lead to a Google Sheet, and sends a demo
outreach email — with follow-up scheduling and execution.

Built as a screening assignment. Plain Python, no frameworks, no database —
the Google Sheet **is** the warehouse.

## Architecture (5 components)

```
Telegram command ─┐
                  ├─> agent.run_pipeline(company, city)
CLI command ──────┘        │
                           ├─ 1. enrich.py      search (DDG → Tavily fallback, cached)
                           │                     strict-JSON LLM extraction (anti-hallucination)
                           ├─ 2. pitch.py       ONE LLM call → fixed 3-line pitch
                           ├─ 3. sheets.py      append/update rows via gog CLI
                           ├─ 4. outreach.py    demo email → test inbox ONLY + follow-up date
                           └─ 5. llm.py         OpenRouter client: model fallback chain,
                                                429-skip, defensive parsing
```

## Usage

```bash
pip install -r requirements.txt

# Chat-style command (as a Telegram bot would relay it)
python agent.py "Find event leads for Zomato in Gurgaon"

# Direct flags
python agent.py --company Zoho --city Chennai

# Rehearsal without side effects (no Sheet write, no email)
python agent.py --company Zoho --city Chennai --dry-run

# Follow-up execution: scan the Sheet for due follow-ups and send them
python agent.py --process-followups            # real send
python agent.py --process-followups --dry-run  # scan only
python agent.py --process-followups --as-of 2026-11-18  # demo/testing hook

# Telegram trigger (only if TELEGRAM_BOT_TOKEN is set)
python telegram_bot.py
```

## Configuration (`.env`, see `.env.example`)

| Key | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | LLM access (required) |
| `OPENROUTER_MODELS` | Comma-separated fallback chain; each model is tried in order, 429s are skipped |
| `GOOGLE_SHEET_ID` | Target spreadsheet |
| `SHEET_TAB` | Tab name (default `lead-demo.csv`) |
| `GOG_EXE` / `GOG_ACCOUNT` | gog CLI path / Google account for Sheets + Gmail |
| `OUTREACH_TO` | Test inbox override (defaults to `GOG_ACCOUNT`) |
| `TELEGRAM_BOT_TOKEN` | Optional — enables the Telegram trigger |
| `TAVILY_API_KEY` | Optional — search fallback when DDG fails |
| `DEBUG_DUMP_RESEARCH` | `true` writes raw search results to `research_data.json` |

## Safety model

- **Outreach never goes to real strangers.** The discovered contact's email is
  quoted in the body for realism; the actual recipient is always the
  operator's own test inbox (`OUTREACH_TO` / `GOG_ACCOUNT`).
- **No fabricated contacts.** The extraction LLM is under a strict JSON
  contract: `null` when a value isn't in the search results, and the code
  *verifies* every claimed email/LinkedIn URL appears verbatim (complete-token
  match) in the snippets before accepting it. A wrong email is worse than a
  missing one — missing contacts produce a graceful
  `contact: LinkedIn URL only` row instead.
- **No LinkedIn scraping.** Search snippets and public pages only.

## LLM output contract

1. **Lead extraction** — one call, strict JSON
   (`{"name", "role", "company", "city", "contact_email", "linkedin_url", "confidence"}`),
   `json.loads` + shape validation with one retry; common key aliases are
   normalized; unparseable after retry → heuristic regex extraction over the
   same snippets → graceful fallback row.
2. **Pitch writer** — one call, exactly 3 lines (≤120 chars each), no
   invented facts, one retry on contract failure, then a deterministic
   fallback pitch.
3. Both calls: temperature 0.2, small max-tokens, model fallback chain with
   429-skip, and defensive parsing (`content` may be `None`; reasoning models
   may emit thinking — detected via `finish_reason=length` and retried with a
   doubled budget instead of being returned as the answer).

## Sheet schema (tab `lead-demo.csv`)

`Date | Company | City | Status | Lead Name | Role | Contact | LinkedIn |
Pitch | Outreach Sent | Follow-up Date`

Status values: `Enriched`, `Enriched (no email — LinkedIn only)`,
`Followed up on <date>`.

## Tests

```bash
python -m pytest tests -q
```

25 unit tests; all external calls (search, LLM, gog subprocess) are mocked —
no network in tests.

## Deliberate scope cuts

No WhatsApp, no LinkedIn scraping, no database/CRM/dedup layer, no hosting,
no UI. The Sheet is the warehouse; the CLI + Telegram command are the only
entrypoints.
