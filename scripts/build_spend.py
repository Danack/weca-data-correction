#!/usr/bin/env python3
"""Normalise WECA quarterly spend files, summarise them, and diff corrections."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "source" / "uploads"
DATA = ROOT / "data"
DIFFS = DATA / "diffs"
REPORT = ROOT / "report"

# Files recovered after the first download pass, so they are absent from
# source/download-results.json.
EXTRA_CSV = [
    {
        "path": "uploads/Transparency-report-First-Quarter-April-2024---June-2024.csv",
        "text": "First Quarter (April 2024 – June 2024) - CSV – original",
        "url": "https://www.westofengland-ca.gov.uk/wp-content/uploads/2024/07/Transparency-report-First-Quarter-April-2024-–-June-2024.csv",
    },
    {
        "path": "uploads/Transparency-Report-Q4-January-2022---March-2022.csv",
        "text": "Fourth Quarter (January 2022 – March 2022) - CSV – original",
        "url": "https://www.westofengland-ca.gov.uk/wp-content/uploads/2022/04/Transparency-Report-Q4-January-2022-–-March-2022.csv",
    },
]

QUARTER_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

HEADER_MAP = {
    "transno": "transaction_no",
    "transactionno": "transaction_no",
    "summaryofpurpose": "purpose",
    "servicearea": "service_area",
    "serarea(t)": "service_area",
    "suppliername": "supplier",
    "supplier": "supplier",
    "supplier/customerid(t)": "supplier",
    "ap/arid(t)": "supplier",
    "date": "doc_date",
    "docdate": "doc_date",
    "trans.date": "doc_date",
    "amount": "amount",
    "irrecoverablevat": "irrecoverable_vat",
}

TX_FIELDS = [
    "financial_year",
    "quarter",
    "version",
    "source_file",
    "source_url",
    "transaction_no",
    "purpose",
    "service_area",
    "supplier",
    "doc_date",
    "amount",
    "irrecoverable_vat",
]


def norm_header(value: str) -> str | None:
    """Map a source column title onto a normalised field name."""
    key = re.sub(r"\s+", "", (value or "")).lower()
    return HEADER_MAP.get(key)


def parse_amount(value: str) -> Decimal | None:
    """Parse a money cell into pounds and pence."""
    text = (value or "").replace("£", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def parse_date(value: str) -> date | None:
    """Parse a day/month/year cell, including spreadsheet datetimes."""
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def quarter_bounds(financial_year: str, quarter: int) -> tuple[date, date]:
    """First and last day of the quarter named on the file."""
    start_year = int(financial_year[:4])
    if quarter == 1:
        return date(start_year, 4, 1), date(start_year, 6, 30)
    if quarter == 2:
        return date(start_year, 7, 1), date(start_year, 9, 30)
    if quarter == 3:
        return date(start_year, 10, 1), date(start_year, 12, 31)
    return date(start_year + 1, 1, 1), date(start_year + 1, 3, 31)


def classify(text: str) -> tuple[str, int, str] | None:
    """Read the financial year, quarter, and version from a download link label."""
    lowered = text.lower().replace("–", "-").replace("—", "-")
    word = re.search(r"\b(first|second|third|fourth)\s+quarter\b", lowered)
    if not word:
        return None
    quarter = QUARTER_WORDS[word.group(1)]
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", lowered)]
    if not years:
        return None
    # The label names the months covered. Q4 is January–March of the
    # second calendar year in a financial year.
    if quarter == 4:
        end_year = max(years)
        financial_year = f"{end_year - 1}/{str(end_year)[2:]}"
    else:
        start_year = min(years)
        financial_year = f"{start_year}/{str(start_year + 1)[2:]}"
    if "original" in lowered:
        version = "original"
    elif in_correction_window(financial_year, quarter):
        version = "corrected"
    else:
        version = "only"
    return financial_year, quarter, version


def in_correction_window(financial_year: str, quarter: int) -> bool:
    """Q1 2020/21 through Q2 2025/26, the period the authority republished."""
    start = int(financial_year[:4])
    order = start * 4 + quarter
    return (2020 * 4 + 1) <= order <= (2025 * 4 + 2)


def select_sources() -> list[dict]:
    """Pick one CSV-labelled file for each quarter and version."""
    results = json.loads((ROOT / "source" / "download-results.json").read_text())
    chosen = []
    for item in results:
        if not item.get("ok"):
            continue
        text = item["text"]
        if "csv" not in text.lower():
            continue
        if classify(text) is None:
            continue
        chosen.append(
            {
                "path": item["path"],
                "text": text,
                "url": item["url"],
            }
        )
    chosen.extend(EXTRA_CSV)
    # One CSV per quarter and version. Prefer a real text file over a
    # workbook that was mislabelled, but keep whichever we have if that
    # is the only copy.
    by_key: dict[tuple, dict] = {}
    for item in chosen:
        meta = classify(item["text"])
        assert meta is not None
        key = meta
        current = by_key.get(key)
        if current is None or _prefer(item, current):
            by_key[key] = item
    return [{**item, "meta": key} for key, item in by_key.items()]


def _prefer(candidate: dict, current: dict) -> bool:
    """Prefer a text file over a workbook when both were saved for the same quarter."""
    cand_path = ROOT / "source" / candidate["path"]
    curr_path = ROOT / "source" / current["path"]
    return _is_text(cand_path) and not _is_text(curr_path)


def _is_text(path: Path) -> bool:
    """True when the file is not an Excel workbook."""
    if not path.exists():
        return False
    raw = path.read_bytes()[:4]
    return not raw.startswith(b"PK") and raw[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def read_rows(path: Path) -> list[list[str]]:
    """Read a CSV, or the first sheet of a workbook, as rows of strings."""
    raw = path.read_bytes()
    if raw.startswith(b"PK"):
        import openpyxl

        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = book.worksheets[0]
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(["" if cell is None else str(cell) for cell in row])
        book.close()
        return rows
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        import xlrd

        book = xlrd.open_workbook(file_contents=raw)
        sheet = book.sheet_by_index(0)
        rows = []
        for r in range(sheet.nrows):
            out = []
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    out.append(xlrd.xldate_as_datetime(cell.value, book.datemode).strftime("%d/%m/%Y"))
                elif cell.ctype == xlrd.XL_CELL_NUMBER:
                    out.append(str(cell.value))
                else:
                    out.append(str(cell.value).strip())
            rows.append(out)
        return rows
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return list(csv.reader(io.StringIO(text, newline="")))


def header_index(rows: list[list[str]]) -> tuple[int, dict[str, list[int]]]:
    """Find the header row and the columns that hold each field."""
    for i, row in enumerate(rows[:8]):
        mapped: dict[str, list[int]] = defaultdict(list)
        for col, cell in enumerate(row):
            name = norm_header(cell)
            if name:
                mapped[name].append(col)
        if "amount" in mapped and "transaction_no" in mapped:
            return i, mapped
    raise ValueError("no header row")


def cell(row: list[str], cols: dict[str, list[int]], name: str) -> str:
    """First non-empty cell among the columns mapped to this field."""
    for index in cols.get(name, []):
        if index < len(row) and row[index].strip():
            return row[index].strip()
    return ""


def load_transactions(sources: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return normalised payments, and the rows that could not be parsed."""
    transactions = []
    issues = []
    for source in sources:
        financial_year, quarter, version = source["meta"]
        path = ROOT / "source" / source["path"]
        try:
            rows = read_rows(path)
            header_at, cols = header_index(rows)
        except Exception as exc:
            issues.append(
                {
                    "financial_year": financial_year,
                    "quarter": quarter,
                    "version": version,
                    "source_file": path.name,
                    "source_url": source["url"],
                    "row_number": "",
                    "problem": f"file: {exc}",
                    "raw": "",
                }
            )
            continue
        for offset, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
            if not any(part.strip() for part in row):
                continue
            amount_raw = cell(row, cols, "amount")
            date_raw = cell(row, cols, "doc_date")
            txn_raw = cell(row, cols, "transaction_no")
            purpose_raw = cell(row, cols, "purpose")
            supplier_raw = cell(row, cols, "supplier")
            # Published files often end with a totals row and nothing else.
            if not any((txn_raw, date_raw, purpose_raw, supplier_raw)):
                continue
            amount = parse_amount(amount_raw)
            doc_date = parse_date(date_raw)
            problems = []
            if amount is None:
                problems.append(f"amount {amount_raw!r}")
            if doc_date is None:
                problems.append(f"date {date_raw!r}")
            record = {
                "financial_year": financial_year,
                "quarter": str(quarter),
                "version": version,
                "source_file": path.name,
                "source_url": source["url"],
                "transaction_no": cell(row, cols, "transaction_no"),
                "purpose": cell(row, cols, "purpose"),
                "service_area": cell(row, cols, "service_area"),
                "supplier": cell(row, cols, "supplier"),
                "doc_date": doc_date.isoformat() if doc_date else "",
                "amount": f"{amount:.2f}" if amount is not None else "",
                "irrecoverable_vat": cell(row, cols, "irrecoverable_vat"),
            }
            if problems:
                issues.append(
                    {
                        "financial_year": financial_year,
                        "quarter": quarter,
                        "version": version,
                        "source_file": path.name,
                        "source_url": source["url"],
                        "row_number": offset,
                        "problem": "; ".join(problems),
                        "raw": " | ".join(row),
                    }
                )
                continue
            transactions.append(record)
    transactions.sort(key=lambda r: (r["financial_year"], int(r["quarter"]), r["version"], r["transaction_no"]))
    return transactions, issues


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    """Write rows to a CSV, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def money(value: Decimal) -> str:
    """Format a decimal as a two-place numeric string."""
    return f"{value:.2f}"


def summarise(transactions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Per-file totals, and a per-year rollup that counts each quarter once."""
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in transactions:
        grouped[(row["financial_year"], int(row["quarter"]), row["version"])].append(row)

    by_file = []
    for key in sorted(grouped):
        financial_year, quarter, version = key
        rows = grouped[key]
        amounts = [Decimal(r["amount"]) for r in rows]
        dates = [date.fromisoformat(r["doc_date"]) for r in rows]
        start, end = quarter_bounds(financial_year, quarter)
        outside = sum(1 for d in dates if d < start or d > end)
        by_file.append(
            {
                "financial_year": financial_year,
                "quarter": quarter,
                "version": version,
                "source_file": rows[0]["source_file"],
                "row_count": len(rows),
                "amount_sum": money(sum(amounts, Decimal("0"))),
                "amount_min": money(min(amounts)),
                "amount_max": money(max(amounts)),
                "date_min": min(dates).isoformat(),
                "date_max": max(dates).isoformat(),
                "rows_outside_quarter": outside,
            }
        )

    preferred: dict[tuple, dict] = {}
    rank = {"corrected": 0, "only": 1, "original": 2}
    for row in by_file:
        key = (row["financial_year"], row["quarter"])
        current = preferred.get(key)
        if current is None or rank[row["version"]] < rank[current["version"]]:
            preferred[key] = row

    by_year_rows: dict[str, list[dict]] = defaultdict(list)
    for row in preferred.values():
        by_year_rows[row["financial_year"]].append(row)

    by_year = []
    for financial_year in sorted(by_year_rows):
        rows = by_year_rows[financial_year]
        versions = sorted({r["version"] for r in rows})
        by_year.append(
            {
                "financial_year": financial_year,
                "version_used": ",".join(versions),
                "quarters": len(rows),
                "row_count": sum(int(r["row_count"]) for r in rows),
                "amount_sum": money(sum((Decimal(r["amount_sum"]) for r in rows), Decimal("0"))),
                "date_min": min(r["date_min"] for r in rows),
                "date_max": max(r["date_max"] for r in rows),
            }
        )
    return by_file, by_year


def row_key(row: dict) -> tuple:
    """Identity used to match the same payment in the original and corrected files."""
    return (
        row["transaction_no"],
        row["amount"],
        row["doc_date"],
        row["supplier"].strip().lower(),
    )


def diff_quarters(transactions: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Write added, removed, and changed rows for each republished quarter."""
    grouped: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in transactions:
        grouped[(row["financial_year"], int(row["quarter"]))][row["version"]].append(row)

    summary = []
    added_all = []
    service_totals: Counter = Counter()
    supplier_totals: Counter = Counter()

    for key in sorted(grouped):
        versions = grouped[key]
        if "corrected" not in versions or "original" not in versions:
            continue
        financial_year, quarter = key
        original = list(versions["original"])
        corrected = list(versions["corrected"])
        orig_counts = Counter(row_key(r) for r in original)
        corr_counts = Counter(row_key(r) for r in corrected)
        matched = orig_counts & corr_counts
        for ident, count in matched.items():
            orig_counts[ident] -= count
            corr_counts[ident] -= count

        orig_left = _take(original, orig_counts)
        corr_left = _take(corrected, corr_counts)

        orig_by_id: dict[str, list[dict]] = defaultdict(list)
        corr_by_id: dict[str, list[dict]] = defaultdict(list)
        for row in orig_left:
            orig_by_id[row["transaction_no"]].append(row)
        for row in corr_left:
            corr_by_id[row["transaction_no"]].append(row)

        changed = []
        added = []
        removed = []
        for txn in sorted(set(orig_by_id) | set(corr_by_id)):
            left = orig_by_id.get(txn, [])
            right = corr_by_id.get(txn, [])
            pair_count = min(len(left), len(right))
            for old, new in zip(left[:pair_count], right[:pair_count]):
                if _same_fields(old, new):
                    continue
                changed.append(_change_row(old, new))
            removed.extend(left[pair_count:])
            added.extend(right[pair_count:])

        stem = f"{financial_year.replace('/', '-')}-q{quarter}"
        write_csv(DIFFS / f"{stem}-added.csv", added, TX_FIELDS)
        write_csv(DIFFS / f"{stem}-removed.csv", removed, TX_FIELDS)
        write_csv(
            DIFFS / f"{stem}-changed.csv",
            changed,
            [
                "financial_year",
                "quarter",
                "transaction_no",
                "original_purpose",
                "corrected_purpose",
                "original_service_area",
                "corrected_service_area",
                "original_supplier",
                "corrected_supplier",
                "original_doc_date",
                "corrected_doc_date",
                "original_amount",
                "corrected_amount",
                "amount_delta",
            ],
        )

        orig_sum = sum((Decimal(r["amount"]) for r in original), Decimal("0"))
        corr_sum = sum((Decimal(r["amount"]) for r in corrected), Decimal("0"))
        added_sum = sum((Decimal(r["amount"]) for r in added), Decimal("0"))
        removed_sum = sum((Decimal(r["amount"]) for r in removed), Decimal("0"))
        changed_delta = sum((Decimal(r["amount_delta"]) for r in changed), Decimal("0"))
        net = corr_sum - orig_sum
        explained = added_sum - removed_sum + changed_delta
        summary.append(
            {
                "financial_year": financial_year,
                "quarter": quarter,
                "original_rows": len(original),
                "corrected_rows": len(corrected),
                "original_sum": money(orig_sum),
                "corrected_sum": money(corr_sum),
                "net_sum": money(net),
                "added_count": len(added),
                "added_sum": money(added_sum),
                "removed_count": len(removed),
                "removed_sum": money(removed_sum),
                "changed_count": len(changed),
                "changed_amount_delta": money(changed_delta),
                "reconciles": "yes" if explained == net else "no",
            }
        )
        for row in added:
            added_all.append(row)
            service_totals[row["service_area"] or "(blank)"] += Decimal(row["amount"])
            supplier_totals[row["supplier"] or "(blank)"] += Decimal(row["amount"])

    by_service = [
        {"service_area": name, "added_sum": money(total)}
        for name, total in service_totals.most_common()
    ]
    by_supplier = [
        {"supplier": name, "added_sum": money(total)}
        for name, total in supplier_totals.most_common(40)
    ]
    return summary, by_service, by_supplier


def _take(rows: list[dict], remaining: Counter) -> list[dict]:
    """Rows still unmatched after exact key matches have been removed."""
    out = []
    for row in rows:
        ident = row_key(row)
        if remaining[ident] > 0:
            remaining[ident] -= 1
            out.append(row)
    return out


def _same_fields(old: dict, new: dict) -> bool:
    """True when purpose, service area, supplier, date, and amount agree."""
    return all(old[name] == new[name] for name in ("purpose", "service_area", "supplier", "doc_date", "amount"))


def _change_row(old: dict, new: dict) -> dict:
    """Side-by-side original and corrected values for one matched payment."""
    delta = Decimal(new["amount"]) - Decimal(old["amount"])
    return {
        "financial_year": new["financial_year"],
        "quarter": new["quarter"],
        "transaction_no": new["transaction_no"],
        "original_purpose": old["purpose"],
        "corrected_purpose": new["purpose"],
        "original_service_area": old["service_area"],
        "corrected_service_area": new["service_area"],
        "original_supplier": old["supplier"],
        "corrected_supplier": new["supplier"],
        "original_doc_date": old["doc_date"],
        "corrected_doc_date": new["doc_date"],
        "original_amount": old["amount"],
        "corrected_amount": new["amount"],
        "amount_delta": money(delta),
    }


def gbp(value: str) -> str:
    """Format a numeric string as pounds for the HTML report."""
    number = Decimal(value)
    sign = "-" if number < 0 else ""
    return f"{sign}£{abs(number):,.2f}"


def html_table(headers: list[tuple[str, str]], rows: list[dict], money_cols: set[str]) -> str:
    """Render a list of rows as an HTML table."""
    head = "".join(f"<th>{label}</th>" for label, _ in headers)
    body = []
    for row in rows:
        cells = []
        for _, key in headers:
            value = row[key]
            text = gbp(str(value)) if key in money_cols else str(value)
            cells.append(f"<td>{escape(text)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def escape(value: str) -> str:
    """Escape text for HTML."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def write_report(
    by_year: list[dict],
    by_file: list[dict],
    diff_summary: list[dict],
    by_service: list[dict],
    by_supplier: list[dict],
    transactions: list[dict],
    issues: list[dict],
) -> None:
    """Write report/index.html from the summary and diff tables."""
    # Largest added payments are read back from the diff files so the
    # report matches what was written.
    added_rows = []
    for path in sorted(DIFFS.glob("*-added.csv")):
        with path.open() as handle:
            added_rows.extend(csv.DictReader(handle))
    added_rows.sort(key=lambda r: Decimal(r["amount"]), reverse=True)
    top_added = added_rows[:30]

    parts = [
        "<!DOCTYPE html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        "<title>WECA spend corrections</title>",
        "<style>",
        "body{font-family:Georgia,serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;}",
        "h1,h2{font-weight:normal;} table{border-collapse:collapse;width:100%;margin:1rem 0 2rem;font-size:0.92rem;}",
        "th,td{border-bottom:1px solid #ccc;text-align:left;padding:0.35rem 0.5rem;vertical-align:top;}",
        "th{font-size:0.8rem;letter-spacing:0.02em;} td:last-child,th:last-child{text-align:right;}",
        "p.note{color:#444;}",
        "</style></head><body>",
        "<h1>West of England Combined Authority spend</h1>",
        "<p>Totals use the corrected quarterly file where the authority republished one, and the only published file otherwise. Originals are not added on top of corrections. Amounts are the published payment amounts, which the authority describes as expenditure over £500.</p>",
        "<h2>By financial year</h2>",
        html_table(
            [
                ("Year", "financial_year"),
                ("Version used", "version_used"),
                ("Quarters", "quarters"),
                ("Payments", "row_count"),
                ("Earliest date", "date_min"),
                ("Latest date", "date_max"),
                ("Total", "amount_sum"),
            ],
            by_year,
            {"amount_sum"},
        ),
        "<h2>Correction by quarter</h2>",
        "<p>Added rows are in the corrected file and not in the original. Removed rows are the reverse. Changed rows share a transaction number but differ in amount, date, supplier, purpose, or service area. Net is the corrected total minus the original total.</p>",
        html_table(
            [
                ("Year", "financial_year"),
                ("Q", "quarter"),
                ("Original", "original_sum"),
                ("Corrected", "corrected_sum"),
                ("Net", "net_sum"),
                ("Added", "added_count"),
                ("Added £", "added_sum"),
                ("Removed", "removed_count"),
                ("Removed £", "removed_sum"),
                ("Changed", "changed_count"),
                ("Change £", "changed_amount_delta"),
                ("Reconciles", "reconciles"),
            ],
            diff_summary,
            {"original_sum", "corrected_sum", "net_sum", "added_sum", "removed_sum", "changed_amount_delta"},
        ),
        "<h2>Added payments by service area</h2>",
        html_table(
            [("Service area", "service_area"), ("Added", "added_sum")],
            by_service,
            {"added_sum"},
        ),
        "<h2>Largest suppliers among added payments</h2>",
        html_table(
            [("Supplier", "supplier"), ("Added", "added_sum")],
            by_supplier,
            {"added_sum"},
        ),
        "<h2>Largest added payments</h2>",
        html_table(
            [
                ("Year", "financial_year"),
                ("Q", "quarter"),
                ("Date", "doc_date"),
                ("Supplier", "supplier"),
                ("Purpose", "purpose"),
                ("Service area", "service_area"),
                ("Amount", "amount"),
            ],
            top_added,
            {"amount"},
        ),
        "<h2>Each published file</h2>",
        "<p class='note'>Rows outside the quarter are payments whose document date falls outside the months named in the file title.</p>",
        html_table(
            [
                ("Year", "financial_year"),
                ("Q", "quarter"),
                ("Version", "version"),
                ("Payments", "row_count"),
                ("Earliest", "date_min"),
                ("Latest", "date_max"),
                ("Outside quarter", "rows_outside_quarter"),
                ("Total", "amount_sum"),
            ],
            by_file,
            {"amount_sum"},
        ),
    ]
    if issues:
        parts.append(f"<h2>Rows that could not be read</h2><p>{len(issues)} rows or files. See data/parse_issues.csv.</p>")
    else:
        parts.append("<h2>Rows that could not be read</h2><p>None.</p>")
    parts.append("</body></html>")
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "index.html").write_text("\n".join(parts))


def main() -> None:
    """Build the transaction table, the summaries, the diffs, and the HTML report."""
    sources = select_sources()
    transactions, issues = load_transactions(sources)
    write_csv(DATA / "transactions.csv", transactions, TX_FIELDS)
    write_csv(
        DATA / "parse_issues.csv",
        issues,
        ["financial_year", "quarter", "version", "source_file", "source_url", "row_number", "problem", "raw"],
    )
    by_file, by_year = summarise(transactions)
    write_csv(
        DATA / "summary_by_file.csv",
        by_file,
        [
            "financial_year",
            "quarter",
            "version",
            "source_file",
            "row_count",
            "amount_sum",
            "amount_min",
            "amount_max",
            "date_min",
            "date_max",
            "rows_outside_quarter",
        ],
    )
    write_csv(
        DATA / "summary_by_year.csv",
        by_year,
        ["financial_year", "version_used", "quarters", "row_count", "amount_sum", "date_min", "date_max"],
    )
    diff_summary, by_service, by_supplier = diff_quarters(transactions)
    write_csv(
        DATA / "diff_summary.csv",
        diff_summary,
        [
            "financial_year",
            "quarter",
            "original_rows",
            "corrected_rows",
            "original_sum",
            "corrected_sum",
            "net_sum",
            "added_count",
            "added_sum",
            "removed_count",
            "removed_sum",
            "changed_count",
            "changed_amount_delta",
            "reconciles",
        ],
    )
    write_csv(DATA / "added_by_service.csv", by_service, ["service_area", "added_sum"])
    write_csv(DATA / "added_by_supplier.csv", by_supplier, ["supplier", "added_sum"])
    write_report(by_year, by_file, diff_summary, by_service, by_supplier, transactions, issues)
    print(f"transactions {len(transactions)} issues {len(issues)} files {len(by_file)} diffs {len(diff_summary)}")
    bad = [r for r in diff_summary if r["reconciles"] != "yes"]
    print("unreconciled", len(bad))


if __name__ == "__main__":
    main()
