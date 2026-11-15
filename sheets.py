"""Google Sheets access via the gog CLI (subprocess). The Sheet IS the warehouse."""
import logging
import subprocess

from config import cfg

log = logging.getLogger("agent.sheets")

HEADERS = [
    "Date", "Company", "City", "Status", "Lead Name", "Role",
    "Contact", "LinkedIn", "Pitch", "Outreach Sent", "Follow-up Date",
]


def _gog(args, timeout=60):
    exe = cfg("GOG_EXE", "gog")
    cmd = [exe] + args
    account = cfg("GOG_ACCOUNT")
    if account:
        cmd += ["-a", account]
    log.info("gog %s", " ".join(args[:3]))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def get_rows(sheet_id=None, range_="A2:K200"):
    """Return existing data rows (list of lists). Empty list on failure."""
    sheet_id = sheet_id or cfg("GOOGLE_SHEET_ID")
    res = _gog(["sheets", "get", sheet_id, range_, "--plain"])
    if res.returncode != 0:
        log.error("sheets get failed: %s", res.stderr.strip()[:300])
        return []
    rows = []
    for line in res.stdout.splitlines():
        line = line.rstrip()
        if line:
            rows.append(line.split("\t"))
    return rows


def append_row(values, sheet_id=None):
    """Append one 11-column row. Returns True on success."""
    sheet_id = sheet_id or cfg("GOOGLE_SHEET_ID")
    if len(values) != len(HEADERS):
        log.error("append_row expects %d values, got %d", len(HEADERS), len(values))
        return False
    # Sanitize: single-line cells (newlines make TSV reads ambiguous)
    clean = [str(v).replace("\r\n", " / ").replace("\n", " / ").strip() for v in values]
    # --values-json avoids delimiter ambiguity (commas/pipes in pitch text)
    import json as _json
    res = _gog(["sheets", "append", sheet_id, "A1", "--values-json", _json.dumps([clean])])
    if res.returncode != 0:
        log.error("sheets append failed: %s", res.stderr.strip()[:300])
        return False
    return True


def find_rows(company=None, city=None):
    """Scan existing rows; return list of (row_number, cells) matching filters."""
    matches = []
    for i, cells in enumerate(get_rows(), start=2):
        padded = cells + [""] * (len(HEADERS) - len(cells))
        if company and padded[1].strip().lower() != company.strip().lower():
            continue
        if city and padded[2].strip().lower() != city.strip().lower():
            continue
        matches.append((i, padded))
    return matches


def update_row(row_num, col_start_idx, values, sheet_id=None):
    """Update cells in an existing row (1-based row, 0-based column index).

    values: list of new values starting at column col_start_idx (A=0).
    Returns True on success. Tries the plain range first, then the
    tab-qualified range (some gog commands require the sheet name).
    """
    sheet_id = sheet_id or cfg("GOOGLE_SHEET_ID")
    col_letter = chr(ord("A") + col_start_idx)
    col_end = chr(ord("A") + col_start_idx + len(values) - 1)
    import json as _json
    payload = _json.dumps([values])
    for range_ in (f"{col_letter}{row_num}:{col_end}{row_num}",
                   f"{cfg('SHEET_TAB', 'lead-demo.csv')}!{col_letter}{row_num}:{col_end}{row_num}"):
        res = _gog(["sheets", "update", sheet_id, range_, "--values-json", payload])
        if res.returncode == 0:
            return True
        log.warning("sheets update %s failed: %s", range_, res.stderr.strip()[:200])
    log.error("sheets update failed for row %d", row_num)
    return False
