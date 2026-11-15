# TASKPAD — Lead Enrichment & Outreach Agent

Created: 2026-11-14 (Fri) · Deadline: 2026-11-16 (Mon) ~17:18 IST
Purpose: screening assignment (event-industry client). Built generic — if rejected, repo + taskpad carry forward as a standalone portfolio project (rename references, keep architecture).

## Deliverables (from the brief)
- [ ] Short screen recording of one end-to-end run
- [ ] Agent config / workflow definition (the skill itself)
- [ ] GitHub repo link

## Phase 0 — Setup (Fri night)
- [x] Sheets/Drive OAuth scope grant via gog (one Allow click) — 2026-11-14 19:05 IST; services=drive,gmail,sheets verified live
- [ ] Repo init under F:\Projects (generic name, feature branch, ATLAS_SCRATCHPAD.md)
- [ ] Pre-vet 3–4 demo companies with findable leads (contact discovery is the top risk)
- [x] Test Google Sheet created — 2026-11-14 19:08 IST; ID 1voWvdr73adU7hm4Wef0F_avD_pHex9X_M7kvfsNNhNQ; read/write round-trip verified via gog (tab name: 'lead-demo.csv', ranges used WITHOUT tab prefix)
- [x] OpenRouter key provisioned in .env (gitignored) — 2026-11-14 19:40 IST; key tested live; model fallback chain set (gemma-4-31b → nemotron-3.5-lightning → ling-3.2-flash, all :free; 429-skip logic required — free tier rate-limits)
- [ ] S creates project's own Telegram bot via BotFather (~2 min) → token into .env TELEGRAM_BOT_TOKEN (not blocking: CLI entrypoint works without it)

## Phase 1 — Build (Sat)
- [ ] Trigger: Telegram command `Find event leads for <company> in <city>` (Sheet-row trigger: cut — task says OR; add later only if time)
- [ ] Enrichment: search company/city event signals → identify Founder/HR/Events lead → extract name/role/contact (ported from agentic-deep-research loop)
- [ ] Graceful fallback when no email found: log row with "contact: LinkedIn URL only"
- [ ] Pitch writer: one LLM call, fixed 3-line template keyed on lead + event context
- [ ] Actuator: append result row to Sheet + send outreach to test inbox/Gmail drafts + schedule follow-up via cronjob
- [ ] No-scope items (explicitly NOT building): WhatsApp, LinkedIn scraping, DB/CRM/dedup, ChromaDB, hosting

## Phase 2 — Demo (Sun)
- [ ] Full dry-run rehearsal (fail cases included)
- [ ] Record screen run (one clean take, ~2–3 min)
- [ ] Write agent-config/workflow doc
- [ ] Repo cleanup: README, .env.example, no secrets

## Phase 3 — Submit (Mon, buffer day)
- [ ] Final package: recording + config + repo link
- [ ] Submit before ~17:18 IST

## Generalization notes (fill if rejected / reusing)
- Strip client-specific pitch template → make it a config field
- Add Sheet-row trigger as second entrypoint
- Candidate rename: lead-outreach-agent

## Log (append as work moves — every entry dated)
- 2026-11-14: taskpad created; design approved by S (Telegram-trigger-only MVP, Atlas stack recommendation: reuse Hermes fleet + gog + agentic-deep-research core)
