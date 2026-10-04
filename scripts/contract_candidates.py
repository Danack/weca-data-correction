#!/usr/bin/env python3
"""Write a page of contract awards beside spend suppliers that share a word.

This is for reading by eye. It does not decide that a contract and a payment
are the same thing.
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "source" / "contracts" / "ods-weca-contracts-tbl.csv"
TRANSACTIONS = ROOT / "data" / "transactions.csv"
OUT = ROOT / "report" / "contract-candidates.html"

STOP = {
    "LTD", "LIMITED", "THE", "AND", "FOR", "PLC", "LLP", "CIC", "UK",
    "WEST", "ENGLAND", "SOLUTIONS", "SERVICES", "SERVICE", "GROUP",
    "COMPANY", "PARTNERS", "PARTNERSHIP",
}


def words(value: str) -> list[str]:
    found = re.findall(r"[A-Za-z][A-Za-z']+", value or "")
    kept = []
    for word in found:
        token = word.upper().replace("'", "")
        if len(token) >= 4 and token not in STOP and token not in kept:
            kept.append(token)
    return kept


def pounds(value: Decimal) -> str:
    return f"£{value:,.0f}"


def main() -> None:
    contracts = list(csv.DictReader(CONTRACTS.open()))
    ref_key = list(contracts[0].keys())[0]
    spend_amount = defaultdict(lambda: Decimal("0"))
    spend_count = defaultdict(int)
    for row in csv.DictReader(TRANSACTIONS.open()):
        if row["version"] == "original":
            continue
        name = (row["supplier"] or "").strip()
        if not name:
            continue
        spend_amount[name] += Decimal(row["amount"] or "0")
        spend_count[name] += 1
    suppliers = list(spend_amount)

    blocks = []
    for contract in contracts:
        tokens = words(contract["Supplier"])
        candidates = []
        for name in suppliers:
            upper = name.upper()
            hit = [token for token in tokens if token in upper]
            if hit:
                candidates.append((spend_amount[name], spend_count[name], name, ", ".join(hit)))
        candidates.sort(reverse=True)
        shown = candidates[:8]
        extra = len(candidates) - len(shown)
        rows = []
        for amount, count, name, hit in shown:
            rows.append(
                "<tr>"
                f"<td>{html.escape(name)}</td>"
                f"<td class='num'>{count}</td>"
                f"<td class='num'>{pounds(amount)}</td>"
                f"<td>{html.escape(hit)}</td>"
                "</tr>"
            )
        if extra > 0:
            rows.append(f"<tr><td colspan='4'>{extra} more suppliers share a word</td></tr>")
        if not rows:
            rows.append("<tr><td colspan='4'>No spend supplier shares a word of four letters or more.</td></tr>")
        value = Decimal(contract["Contract value"] or "0")
        blocks.append(
            "<article>"
            f"<h2>{html.escape(contract['Supplier'] or '(no supplier)')}</h2>"
            "<p>"
            f"{html.escape(contract[ref_key] or '')} · {html.escape(contract['Contract title'] or '')}<br>"
            f"{pounds(value)} · {html.escape(contract['Contract start date'] or 'no start')} to {html.escape(contract['Contract end date'] or 'no end')}"
            f" · words used: {html.escape(', '.join(tokens) or 'none')}"
            "</p>"
            "<table><thead><tr><th>Spend supplier</th><th class='num'>Payments</th><th class='num'>Spend</th><th>Shared word</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
            "</article>"
        )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Contract awards beside spend suppliers</title>
<style>
body {{ font: 15px/1.4 system-ui, sans-serif; margin: 1.5rem; color: #1c1917; }}
article {{ border-top: 1px solid #d6d3d1; padding: 1rem 0; }}
h1 {{ font-size: 1.4rem; }}
h2 {{ font-size: 1.05rem; margin: 0 0 0.3rem; }}
p {{ margin: 0 0 0.6rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 0.2rem 0.6rem 0.2rem 0; vertical-align: top; }}
th {{ color: #57534e; font-weight: 600; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
</style>
</head>
<body>
<h1>Contract awards beside spend suppliers</h1>
<p>Each block is one row from the contracts file. Under it are suppliers in the corrected and only-version spend files whose name contains a word from the contract supplier. A shared word is not a match.</p>
{''.join(blocks)}
</body>
</html>
"""
    OUT.write_text(page)
    print(OUT, len(contracts))


if __name__ == "__main__":
    main()
