"""Lead Enrichment & Outreach Agent — CLI entrypoint.

Usage:
  python agent.py "Find event leads for Zomato in Gurgaon"
  python agent.py --company Zomato --city Gurgaon [--dry-run]
  python agent.py --process-followups [--dry-run]
"""
import argparse
import datetime as dt
import logging
import re
import sys

import config
import enrich
import outreach
import pitch
import sheets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("agent")

COMMAND_RE = re.compile(
    r"find event leads for (?P<company>.+?) in (?P<city>.+?)\s*$", re.IGNORECASE
)


def parse_command(text):
    """Parse 'Find event leads for <company> in <city>' -> (company, city) or None."""
    m = COMMAND_RE.search(text.strip())
    if not m:
        return None
    return m.group("company").strip(), m.group("city").strip()


def run_pipeline(company, city, dry_run=False):
    """Enrich -> pitch -> sheet row -> outreach -> follow-up date. Returns result dict."""
    result = {"company": company, "city": city, "dry_run": dry_run}
    print(f"\n=== Lead Enrichment & Outreach Agent ===")
    print(f"Target: {company} ({city})" + ("  [DRY RUN]" if dry_run else ""))

    # 1. Enrich
    print("\n[1/4] Searching for event signals and lead contact info...")
    lead = enrich.enrich(company, city)
    result["lead"] = {k: v for k, v in lead.items() if k != "snippets"}
    n_signals = len(lead.get("event_signals") or [])
    print(f"  Search signals gathered: {n_signals}")
    print(f"  Lead: {lead['name']} — {lead['role']} (confidence: {lead.get('confidence', '-')})")
    print(f"  Email: {lead['email'] or '(none found)'}")
    print(f"  LinkedIn: {lead['linkedin'] or '(none found)'}")

    # 2. Pitch (one LLM call)
    print("\n[2/4] Writing 3-line pitch (one LLM call)...")
    pitch_text = pitch.write_pitch(company, city, lead)
    result["pitch"] = pitch_text
    print("  ---")
    for line in pitch_text.splitlines():
        print(f"  {line}")
    print("  ---")

    # 3. Sheet row
    contact = lead["email"] or (lead["linkedin"] if lead["linkedin"] else "contact: LinkedIn URL only")
    status = "Enriched" if lead["email"] else "Enriched (no email — LinkedIn only)"
    row = [
        dt.date.today().isoformat(), company, city, status,
        lead["name"], lead["role"], contact, lead["linkedin"],
        pitch_text.replace("\n", " / "), "NO", "",
    ]
    print("\n[3/4] Logging to Google Sheet...")
    if dry_run:
        print("  (dry-run) row not appended")
        result["sheet"] = "dry-run"
    else:
        ok = sheets.append_row(row)
        result["sheet"] = "appended" if ok else "FAILED"
        print(f"  {'Row appended.' if ok else 'Sheet append FAILED — see log.'}")

    # 4. Outreach to test inbox + follow-up date
    print("\n[4/4] Outreach (to test inbox only) + follow-up scheduling...")
    if dry_run:
        subject, body = outreach.outreach_email(lead, company, city, pitch_text)
        print(f"  (dry-run) would send to {outreach.test_inbox()}: {subject}")
        result["outreach"] = "dry-run"
    else:
        sent, detail = outreach.send_outreach(lead, company, city, pitch_text)
        result["outreach"] = "sent" if sent else f"FAILED: {detail}"
        print(f"  {'Outreach sent to test inbox.' if sent else 'Outreach FAILED: ' + detail}")
        if sent:
            fdate = outreach.followup_date()
            result["followup_date"] = fdate
            print(f"  Follow-up scheduled: {fdate} (run --process-followups on/after that date)")
            # Write Outreach Sent=YES + Follow-up Date back into the appended row
            matches = sheets.find_rows(company=company, city=city)
            if matches:
                row_num = matches[-1][0]
                if sheets.update_row(row_num, 9, ["YES", fdate]):
                    print(f"  Sheet row {row_num} updated: Outreach Sent=YES, Follow-up={fdate}")
                else:
                    print("  WARNING: could not update Outreach Sent/Follow-up Date in the Sheet")
            else:
                print("  WARNING: appended row not found for follow-up update")

    print("\nDone." if not result["sheet"] == "FAILED" else "\nDone (with errors).")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lead Enrichment & Outreach Agent")
    parser.add_argument("command", nargs="*", help='e.g. "Find event leads for Zomato in Gurgaon"')
    parser.add_argument("--company")
    parser.add_argument("--city")
    parser.add_argument("--process-followups", action="store_true")
    parser.add_argument("--as-of", help="evaluate follow-up due-ness as of this date (YYYY-MM-DD); for testing/demo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.process_followups:
        print("Processing due follow-ups...")
        actions = outreach.process_followups(today=args.as_of, send=not args.dry_run)
        if not actions:
            print("No due follow-ups found.")
        for a in actions:
            print(f"  row {a['row']}: {a['company']} ({a['city']}) due {a['due']} -> {a['detail']}")
        return 0

    company, city = args.company, args.city
    if not company and args.command:
        parsed = parse_command(" ".join(args.command))
        if parsed:
            company, city = parsed
    if not company or not city:
        parser.error('provide a command like "Find event leads for Zomato in Gurgaon" '
                     "or --company X --city Y")

    result = run_pipeline(company, city, dry_run=args.dry_run)
    return 0 if result["sheet"] != "FAILED" else 1


if __name__ == "__main__":
    config.load_env()
    sys.exit(main())
