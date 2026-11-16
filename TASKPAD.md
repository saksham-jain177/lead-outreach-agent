# TASKPAD — Lead Enrichment & Outreach Agent

Created: 2026-11-14 (Fri) · Deadline: 2026-11-16 (Mon) ~17:18 IST
Purpose: screening assignment (event-industry client). Built generic — if rejected, repo + taskpad carry forward as a standalone portfolio project (rename references, keep architecture).

## Deliverables (from the brief)
- [ ] Short screen recording of one end-to-end run
- [x] Agent config / workflow definition (the skill itself) — README.md serves as the deliverable doc
- [ ] GitHub repo link

## Phase 0 — Setup (Fri night)
- [x] Sheets/Drive OAuth scope grant via gog (one Allow click) — 2026-11-14 19:05 IST; services=drive,gmail,sheets verified live
- [x] Repo init under F:\Projects (generic name, feature branch, ATLAS_SCRATCHPAD.md) — 2026-11-15; branch feat/agent-core, 3 commits, clean tree
- [x] Pre-vet 3–4 demo companies with findable leads (contact discovery is the top risk) — 2026-11-15; Zomato/Gurgaon (Deepinder Goyal, live-verified), Zoho/Chennai (Sridhar Vembu, live-verified), Freshworks/Chennai (Girish Mathrubootham), Razorpay/Bengaluru (Harshil Mathur)
- [x] Test Google Sheet created — 2026-11-14 19:08 IST; ID 1voWvdr73adU7hm4Wef0F_avD_pHex9X_M7kvfsNNhNQ; read/write round-trip verified via gog (tab name: 'lead-demo.csv', ranges used WITHOUT tab prefix)
- [x] OpenRouter key provisioned in .env (gitignored) — 2026-11-14 19:40 IST; key tested live; model fallback chain set (gemma-4-31b → nemotron-3.5-lightning → ling-3.2-flash, all :free; 429-skip logic required — free tier rate-limits)
- [x] S creates project's own Telegram bot via BotFather (~2 min) → token into .env TELEGRAM_BOT_TOKEN — 2026-11-14 20:05 IST; @gopratlebot (id 9279493915), getMe verified live. NOTE: S must press Start on t.me/gopratlebot once before the bot can DM them (demo prerequisite)
- [x] Bot→S round-trip verified — 2026-11-14 20:10 IST; S started the bot (<operator>, id 987654321); sendMessage delivered (message_id 2). TELEGRAM_CHAT_ID=987654321 added to .env for listener auth + reply target

## Phase 1 — Build (Sat)
- [x] Trigger: Telegram command `Find event leads for <company> in <city>` (Sheet-row trigger: cut — task says OR; add later only if time) — 2026-11-15; telegram_bot.py listener locked to TELEGRAM_CHAT_ID (operator-only, 2 auth tests) + CLI entrypoint
- [x] Enrichment: search company/city event signals → identify Founder/HR/Events lead → extract name/role/contact — 2026-11-15; strict-JSON extraction + snippet-verbatim verification (caught a real truncation bug 'l@gmail.com'), LLM skipped entirely when search returns nothing
- [x] Graceful fallback when no email found: log row with "contact: LinkedIn URL only" — 2026-11-15; exercised in the live run (Deepinder Goyal row: LinkedIn URL in Contact, no fabricated email)
- [x] Pitch writer: one LLM call, fixed 3-line template keyed on lead + event context — 2026-11-15; exactly-3-lines + ≤120 chars + no-invented-facts validation, retry-once, temp 0.2
- [x] Actuator: append result row to Sheet + send outreach to test inbox/Gmail drafts + schedule follow-up — 2026-11-15; switched to --values-json after comma-mangling incident; post-send write-back (Outreach Sent=YES, Follow-up Date); --process-followups mode verified live
- [x] No-scope items (explicitly NOT building): WhatsApp, LinkedIn scraping, DB/CRM/dedup, ChromaDB, hosting

## Phase 2 — Demo (Sun)
- [ ] Full dry-run rehearsal (fail cases included)
- [ ] Record screen run (one clean take, ~2–3 min)
- [x] Write agent-config/workflow doc — README.md
- [x] Repo cleanup: README, .env.example, no secrets — verified 2026-11-15: .env gitignored, requirements.txt present, 27/27 tests pass

## Phase 3 — Submit (Mon, buffer day)
- [ ] Final package: recording + config + repo link
- [ ] Submit before ~17:18 IST

## Generalization notes (fill if rejected / reusing)
- Strip client-specific pitch template → make it a config field
- Add Sheet-row trigger as second entrypoint
- Candidate rename: lead-outreach-agent
- Bot username @gopratlebot is client-branded → recreate a generic bot on reuse

## Log (append as work moves — every entry dated)
- 2026-11-14: taskpad created; design approved by S (Telegram-trigger-only MVP, Atlas stack recommendation: reuse Hermes fleet + gog + agentic-deep-research core)
- 2026-11-14 ~19:45 IST: Atlas briefed with full build brief (delivery 4515c023...); strict-LLM-output addendum sent (no fabricated emails, 3-line pitch validation); Atlas target_state=working
- 2026-11-15 16:06 IST: repo snapshot — 8 modules + tests/ written on feat/agent-core, code uncommitted, Atlas actively debugging tests (self-caught mangled think-tag in test file, fixing via programmatic tag construction). On schedule for Sat build / Sun rehearsal / Mon submit.
- 2026-11-15 ~17:00 IST: ATLAS BUILD COMPLETE — Hermes verification: 27/27 tests pass (6.3s); Sheet demo row live (Zomato/Gurgaon/Deepinder Goyal, fallback path exercised, no fabricated email); 4 [DEMO] emails in S's own inbox incl. [DEMO][Follow-up] (follow-up execution mode proven); README + requirements present; feat/agent-core 3 commits, no push. Atlas checkout accident cost 4 taskpad lines — re-applied with this entry. Remaining: rehearsal + recording (Sun), GitHub push (needs S say-so), submit (Mon).
- 2026-11-15 ~17:30 IST: Rehearsal started. Found + fixed: (1) pitch validator accepted truncated 3rd line ("Would") → Atlas fixed fbc320c (min 30 chars/line + sentence punctuation, max_tokens 300→400); Hermes-verified 29/29 tests + Freshworks & Zomato dry-runs now produce complete pitches. (2) telegram_bot.py crashed on startup (NameError: config) → Hermes patched missing `import config` (one line, uncommitted — Atlas to fold into next commit).
- 2026-11-15 ~19:35 IST: Telegram live test #1 (Zoho/Chennai) — pipeline completed end-to-end (row + outreach + follow-up + write-back) BUT search silently degraded: listener ran under wrong python (no ddg) AND duckduckgo_search pkg is deprecated/renamed to `ddgs` (silent 0-result rate-limit behavior). Fixes: listener restarted under py -3.11 (has ddg); enrich.py import switched to `ddgs` with legacy fallback (Hermes patch, uncommitted); requirements.txt updated ddgs>=9.0.0. Verified: Razorpay/Bengaluru dry-run now search-backed (Harshil Mathur, confidence 0.75, source-redacted email hxxx@razorpay.com — no masking in code, honest as-found data). Telegram reply format confirmed camera-clean. Listener running: proc_3e4bb7530183 (py -3.11).
