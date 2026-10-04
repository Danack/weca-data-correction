#!/usr/bin/env python3
"""Assign differing payments to named groups and write the group report."""

from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIFFS = ROOT / "data" / "diffs"
GROUPS = ROOT / "groups"
REPORT = ROOT / "report" / "groups.html"

MINISTRY = (
    "ministry of housing",
    "mhclg",
)


def clean(value: str) -> str:
    return (value or "").replace("\ufffd", "e").replace("\uFFFD", "e").strip()


def money(value: Decimal) -> str:
    """Format a decimal as a two-place numeric string."""
    return f"{value:.2f}"


def pounds(value: Decimal) -> str:
    """Format a decimal as pounds with thousands separators."""
    return f"£{value:,.2f}"


def load_diff(kind: str) -> list[dict]:
    """Read one combined diff file into display rows."""
    path = DIFFS / f"all-{kind}.csv"
    rows = []
    for raw in csv.DictReader(path.open()):
        if kind == "changed":
            row = {
                "kind": kind,
                "financial_year": raw["financial_year"],
                "quarter": raw["quarter"],
                "transaction_no": raw["transaction_no"],
                "date": raw["corrected_doc_date"],
                "supplier": clean(raw["corrected_supplier"]),
                "original_supplier": clean(raw["original_supplier"]),
                "purpose": clean(raw["corrected_purpose"]),
                "original_purpose": clean(raw["original_purpose"]),
                "service_area": clean(raw["corrected_service_area"]),
                "original_service_area": clean(raw["original_service_area"]),
                "amount": money(Decimal(raw["corrected_amount"])),
                "original_amount": money(Decimal(raw["original_amount"])),
            }
        else:
            row = {
                "kind": kind,
                "financial_year": raw["financial_year"],
                "quarter": raw["quarter"],
                "transaction_no": raw["transaction_no"],
                "date": raw["doc_date"],
                "supplier": clean(raw["supplier"]),
                "purpose": clean(raw["purpose"]),
                "service_area": clean(raw["service_area"]),
                "amount": money(Decimal(raw["amount"])),
            }
        rows.append(row)
    return rows


def member(row: dict) -> dict:
    """The fields that identify one payment inside a group file."""
    return {
        "financial_year": row["financial_year"],
        "quarter": row["quarter"],
        "transaction_no": row["transaction_no"],
        "date": row["date"],
        "amount": row["amount"],
        "supplier": row["supplier"],
    }


def is_ministry(supplier: str) -> bool:
    lowered = supplier.lower()
    return any(part in lowered for part in MINISTRY)


def is_added_purpose(row: dict, purpose: str) -> bool:
    return row["kind"] == "added" and row["purpose"] == purpose


def is_transport_operator(row: dict) -> bool:
    """Added payments whose purpose is Transport Operators."""
    return is_added_purpose(row, "Transport Operators")


def is_capital_grant(row: dict) -> bool:
    """Added capital grants, plus payments to government departments under Agencies or Public Bodies."""
    if row["kind"] != "added":
        return False
    purpose = row["purpose"]
    return purpose == "Capital Grants" or purpose == "Agencies or Public Bodies"


def is_core_monthly(row: dict) -> bool:
    return (
        row["kind"] == "added"
        and row["service_area"] == "Core Funding"
        and row["purpose"] == "Government Departments"
    )


def is_central_monthly(row: dict) -> bool:
    if row["kind"] != "added" or row["service_area"] != "Funding from Central Government":
        return False
    if row["purpose"] != "Government Departments":
        return False
    supplier = row["supplier"].lower()
    return supplier == "bristol city council" or is_ministry(row["supplier"])


def letters(value: str) -> str:
    """Letters and digits only, for comparing supplier names."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def is_atkins(row: dict) -> bool:
    """Atkins Limited and AtkinsRéalis, including the accent lost as a replacement character."""
    names = [row.get("supplier", "")]
    if row["kind"] == "changed":
        names.append(row.get("original_supplier", ""))
    for name in names:
        folded = name.replace("é", "e").replace("É", "E").replace("è", "e").replace("È", "E")
        compact = letters(folded)
        if "ATKINSREALIS" in compact or compact.startswith("ATKINSLIMITED"):
            return True
    return False


def is_missed_publishing(row: dict) -> bool:
    """Suppliers whose omitted payments are being gathered into Missed publishing."""
    for name in (row.get("supplier", ""), row.get("original_supplier", "")):
        compact = letters(name)
        if "FELINESOFT" in compact or "CLEARCOURSE" in compact:
            return True
        if "AECOM" in compact and row["kind"] in ("added", "removed"):
            return True
        if compact == "NORTHSOMERSETCOUNCIL":
            return True
        if compact in ("AVONPENSIONFUND", "BATHNORTHEASTSOMERSETCOUNCILGENERALSUSPSENSEACCOUNT"):
            return True
        if any(token in compact for token in (
            "CARLISLESTAFFING",
            "GUIDANTGLOBAL",
            "BUILDINGRESEARCHESTABLISHMENT",
            "PLACECUBE",
            "PIXIEENERGY",
            "OPINIONRESEARCHSERVICES",
            "COMENSURA",
        )):
            return True
        if "CONSTELLIA" in compact and row["kind"] == "added":
            return True
        if compact in (
            "DATACUBEDLTD",
            "GLOUCESTERSHIRECOUNTYCOUNCIL",
            "GRAHAMTATETAEXCEPTIONALDEVELOPMENT",
            "GRANTTHORNTON",
            "GRANTTHORNTONUKLLP",
            "HMRC",
            "ICO",
            "SOUTHGLOUCESTERSHIRECOUNCIL",
            "UNIVERSITYOFBATH",
            "UNIVERSITYOFTHEWESTOFENGLAND",
            "WSPUKLIMITED",
        ):
            return True
        if "SPARKSOUTHWEST" in compact:
            return True
    return False


def is_individual_1(row: dict) -> bool:
    """Any payment whose original or corrected supplier is Y E Elsorougi."""
    for name in (row.get("supplier", ""), row.get("original_supplier", "")):
        if "ELSOROUGI" in letters(name):
            return True
    return False


def is_transport_rename(row: dict) -> bool:
    """Already published payments renamed for C T Coaches, The Big Lemon, or Eurotaxis."""
    if row["kind"] != "changed":
        return False
    for name in (row.get("supplier", ""), row.get("original_supplier", "")):
        compact = letters(name)
        if any(token in compact for token in ("CTCOACHES", "BIGLEMON", "EUROTAXIS", "EUROCOACHES", "FARESAVER", "TURNERSCOACHWAYS", "CLICKTRAVEL", "PERKUK")):
            return True
    return False


def is_redacted_name(value: str) -> bool:
    return bool(value and re.search(r"redact", value, re.IGNORECASE))


NAMED_UNREDACTIONS = (
    "GRAHAMTATE",
    "JEANVERNON",
    "BRISTOLBIKEPROJECT",
)

REDACTED_TO_CLOSED = (
    "CIRQUEBIJOU",
    "CALYO",
    "AUROCH",
    "BILLSHARPE",
    "ANDREPATTENDEN",
    "ZLATISPASOVA",
    "VICTORIABOURNE",
    "ADAMGASSON",
    "ANNABARCLAY",
    "AVONWILDLIFE",
    "BATHCITYFARM",
    "BRIONYPHILLIPS",
    "BUCKMANASSOCIATES",
    "BOLANYON",
    "HEXPRODUCTIONS",
    "JESSICATHORN",
    "KINGSCHAMBERS",
    "KATYWELSH",
    "MADEMYWARDROBE",
    "HOBBSWINDOW",
    "HARRYCOBBOLD",
    "MAYKTHEATRE",
    "MRAJRICHARDS",
    "MSDJROBINSON",
    "NALTAHHAN",
    "FREIATURLAND",
    "JONESMILLBANK",
    "NGDADVISORY",
    "ROZSTEWART",
    "PROJICT",
    "COLMWATLING",
    "HADAVIZADEH",
    "FLINTINNOVATION",
    "LAURAWILLIAMS",
    "ELECTEDTECHNOLOGIES",
    "PHILCHAMBERLAIN",
    "PRESENTATIONMAESTRO",
    "FRANCISTAYLOR",
    "GERARDLISTON",
    "COGNITIVEPATHS",
    "DIVAAGENCY",
    "CENTREFORSUSTAINABLEENERGY",
    "BRISTOLJAZZANDBLUES",
    "CARRUTHERSTANNER",
    "CENTREFORCITIES",
    "CREATIVITYWORKS",
    "DELOITTEMCS",
    "ESTERDEROIJ",
    "GREATCOPYMATTERS",
    "ANDYCOUNCIL",
    "ANNASMITHSON",
    "CLAREDISTON",
    "COLINKING",
    "KATYCONNOR",
    "JESSICAAUGARDE",
    "JONAITKEN",
    "CLOSEDMOORE",
    "INTEGRATIVEMEDICINE",
    "RAUCOUS",
    "GREENREGISTER",
    "CARMELBRISTOL",
    "DANIELWOODASSOCIATES",
    "CLOSEDPETROC",
    "FRAZERMEAKING",
    "HAWKESBURYVOLUNTEER",
    "LEONARDCHESHIRE",
    "RUTHGERRARD",
    "SPARKFILMS",
    "SPRINTPRINT",
    "MUSUEMOFEASTASIAN",
    "TIMSCOONES",
    "AJBELSHAW",
    "NICKYOUNG",
    "ARIMACONSULTING",
    "ATOMICSMASH",
    "NEXTVENTURESTUDIO",
    "INVISIBLECIRCUS",
    "CHRISHACKETT",
    "ESTHERSHELLEY",
    "MARSHFIELDCOMMUNITY",
    "PAULGILLIS",
    "CRAFTYHEN",
    "LANDORLINKS",
    "REDCATCHCOMMUNITY",
)


def is_named_unredaction(row: dict) -> bool:
    """Redacted - Sole Trader corrected to one of three named suppliers."""
    if row["kind"] != "changed" or not is_redacted_name(row.get("original_supplier", "")):
        return False
    compact = letters(row.get("supplier", ""))
    return any(token in compact for token in NAMED_UNREDACTIONS)


def is_redacted_supplier(row: dict) -> bool:
    """An already published payment whose corrected supplier name is a redaction."""
    if row["kind"] != "changed":
        return False
    if is_redacted_name(row.get("supplier", "")):
        return True
    if not is_redacted_name(row.get("original_supplier", "")):
        return False
    compact = letters(row.get("supplier", ""))
    return any(token in compact for token in REDACTED_TO_CLOSED)


def is_listed_name_change(row: dict) -> bool:
    """Supplier pairs identified by hand, where the CLOSED prefix test does not match."""
    if row["kind"] != "changed":
        return False
    original = letters(row.get("original_supplier", ""))
    corrected = letters(row.get("supplier", ""))
    pairs = (
        ("ALTONIANCOACHES", "ALTONIANCOACHES"),
        ("BRISTOLCOMMUNITYENERGY", "BRISTOLCOMMUNITYENERGY"),
        ("ROWEIT", "CACI"),
        ("SOCITMADVISORY", "CIVITEQ"),
        ("FUTURELEAPLIMITED", "FUTURELEAPES"),
        ("DESTINATIONBRISTOLTAVISITWEST", "VISITWESTLIMITED"),
        ("PECTRUST", "PLYMOUTHENERGY"),
        ("11KBWLTDJGQC", "11KBWLTDJGKC"),
        ("CLEARREVIEW", "ADVANCEDBUSINESSSOFTWARE"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "AVINELECTRONICS"),
        ("BRITSOLPAYJI", "BRISTOLPAYJI"),
        ("BRISTOLGREENCAPITAL", "BRISTOLCLIMATEANDNATURE"),
        ("HCTGROUPOPERATIONSCICPREVIOUSLY", "HCTGROUP"),
        ("WALLERANDWOOD", "NOWALKINGCANVAS"),
        ("ADYOUNGTECHNICAL", "SEE601499"),
        ("ACTINGAGENTSFORWECA", "WESTOFENGLANDCOMBINEDAUTHORITY"),
        ("KNOWLEWESTMEDIACENTRE", "REGISTEREDCHARITY"),
        ("ANATOMYSTUDIOLTD", "OKUDESIGN"),
        ("SQUAREBIRDLLP", "SQUAREBIRDAGENCY"),
        ("PKGROUPVENTURES", "PKFINANCIAL"),
        ("ECONOMICMODELLING", "ECONOMICMODELING"),
        ("SOLACEINBUSINESSLTD", "RECRUITMENTINTERIM"),
        ("TEAMTELEMARETING", "TEAMTELEMARKETING"),
        ("PYTCHLIMITED", "SEE601648"),
        ("SSGREATBRITAINTRADINGLTD", "CATERINGSEE601422"),
        ("DESTINATIONBRISTOL", "VISITWESTLIMITED"),
        ("MAYDENHOUSELTD", "MAYDENHOUSELIMITED"),
        ("JEKKASLIMITED", "JEKKASLIMITED"),
        ("JEKKAESLIMITED", "JEKKASLIMITED"),
        ("STHELENSCHURCHALVESTON", "STHELENSCHURCHALVESTON"),
        ("KATESKITCHENCATERING", "KATESKITCHENCATERING"),
        ("KATEESKITCHEN", "KATESKITCHEN"),
        ("KATESKITCHENCATERING", "KATEESKITCHEN"),
        ("SUITEDANDBOOTED", "SBORIGINALS"),
        ("CH2MHILL", "JACOBSUK"),
        ("SPARKSOUTHWESTLTD", "SPARKSOUTHWEST"),
        ("SOMERSETCOUNTYCOUNCIL", "SOMERSETCOUNCIL"),
        ("11KBWLTD", "11KBWLTD"),
        ("BRISTOLMUSICTRUST", "BMTENTERPRISES"),
        ("CENTREFORPUBLICSCRUTINY", "CENTREFORGOVERNANCEANDSCRUTINY"),
        ("IANJOHNSONTACHEWVALLEYGATES", "CHEWVALLEYGATES"),
        ("ECUITYADVISORY", "SECUITYADVISORY"),
        ("BRISTOLSPACEWORKS", "BRISTOLSPACEWORKSLTD"),
        ("CABINETOFFICENATIONALFRAUD", "CABINETOFFICE"),
        ("BATHPROPERTYMAINTENANCE", "BPMCONTRACTING"),
        ("WESTOFENGLANDROBOTICSNETWORK", "SEE600086"),
        ("OBJECTIVE", "GERARDLISTON"),
        ("STBRENDANES", "STBRENDANS"),
        ("TACSQUARED", "DAYTODAYPROJMNG"),
        ("DTWADVERTISING", "DTWCOMMUNICATIONS"),
        ("EALINCLUSIVELTC", "EALINCLUSIVELTD"),
        ("EAVSOLUTIONS", "ELECTRICASSISTEDVEHICLES"),
        ("MAZARSLLP", "FORVISMAZARS"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "FOWLERSOFBRISTOL"),
        ("GLOBALRADIOSERVICES", "GLOBALMEDIAGROUP"),
        ("JOHNWESLEYES", "JOHNWESLEYS"),
        ("KELPINDUSTRIES", "BUSINESSINNOVATION"),
        ("FARMINK", "LEARNINK"),
        ("WPDTELECOMS", "NATIONALGRIDTELECOMS"),
        ("RWKGOODMNAN", "RWKGOODMAN"),
        ("EVELYNPARTNERSHIP", "SWPARTNERS"),
        ("SUNDRYSUPPLIERGENERAL", "SAFERSHOPS"),
        ("COALAUTHORITY", "MININGREMEDIATION"),
        ("ELIORUKPLC", "CATERINGFORSSGBTL"),
        ("WOMENESWORKLAB", "WOMENSWORKLAB"),
        ("WOMENSWORKLAB", "WOMENSWORKLAB"),
        ("DIVERSEARTISTSNETWORKCIC", "DIVERSEARTISTSNETWORK"),
        ("CREATIVESHIFTCIC", "CREATIVESHIFTCIC"),
        ("CISVALLEYSWASTE", "VALLEYSWASTESERVICES"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "SOMERSETTOILETRY"),
        ("SUSTRANS", "WALKWHEELCYCLETRUST"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "STAPLEBARN"),
        ("MOMENTUMSCOOTERS", "SUPERSMITH"),
        ("SOCIALDETAIL", "ARIMACONSULTING"),
        ("OASISACADEMYBRISLINGTON", "OASISSOUTHBRISTOL"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "CONTRASTTIMBERS"),
        ("CISCONSTELLIA", "CONSTELLIAPUBLIC"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "FORMADOME"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "INDEPENDENTCOMPOSITES"),
        ("DIGITALADVISORYSERVICES", "NGDADVISORY"),
        ("THEAGENCYGLOBALLTD", "AGENCYUK"),
        ("TAPRISM", "BUSINESSSUPPLIESGROUP"),
        ("CONSERVATIVEVOLUNTEERS", "CONSERVATIONVOLUNTEERS"),
        ("REEDBUSINESSINFORMATION", "LNRSDATA"),
        ("OMNIGENIX", "NICHOLASSTURGE"),
        ("RYMARSERVICES", "CISRYMAR"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "CLIFTONPHOTONICS"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "SASSYSCENTS"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "COUNTERCULTUREDRINKS"),
        ("SMARTERSHOWSTARSUS", "SMARTERSHOWSLTD"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "TRUPLECOROAST"),
        ("SUNDRYSUPPLIERMADESMARTERGRANTS", "RENNCONSULTANCY"),
    )
    if any(left in original and right in corrected for left, right in pairs):
        return True
    return "PRINCESTRUST" in original and "PRINCE" in corrected and "TRUST" in corrected


def is_closed_rename(row: dict) -> bool:
    """Corrected name is the original name with CLOSED in front, allowing truncation."""
    if is_named_unredaction(row) or is_listed_name_change(row):
        return True
    if row["kind"] != "changed":
        return False
    corrected = row["supplier"]
    if not re.match(r"(?i)^CLOSED\b", corrected):
        return False
    stripped = re.sub(r"(?i)^CLOSED\s*[-–]?\s*", "", corrected)
    original = letters(row.get("original_supplier", ""))
    renamed = letters(stripped)
    if not original or not renamed:
        return False
    return original.startswith(renamed) or renamed.startswith(original)


def already_published(service_area: str) -> Decimal:
    """Corrected total for this service area, minus the payments that were added."""
    corrected = Decimal("0")
    for raw in csv.DictReader((ROOT / "data" / "transactions.csv").open()):
        if raw["version"] == "corrected" and clean(raw["service_area"]) == service_area:
            corrected += Decimal(raw["amount"])
    added = Decimal("0")
    for raw in csv.DictReader((DIFFS / "all-added.csv").open()):
        if clean(raw["service_area"]) == service_area:
            added += Decimal(raw["amount"])
    return corrected - added


def assign(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply the group rules. Earlier groups win when a payment matches more than one.

    Named suppliers and other specific groups are listed before generic ones
    (a purpose such as Grants, a CLOSED prefix, or a redaction), so the specific group wins.
    """
    rules = [
        (
            "missed-publishing",
            "Missed publishing",
            "Payments omitted from the originally published reports. Includes Felinesoft Ltd, both added payments labelled CLOSED Clearcourse Membership Services Ltd (Felinesoft) and published payments renamed to that name, AECOM payments that were added or removed, payments to North Somerset Council, payments to Avon Pension Fund, and payments to Bath & North East Somerset Council General Suspense Account, including the published payment renamed to Bristol City Council. There are no changed AECOM payments in the diff. North Somerset Enterprise Agency is not included. Also Carlisle Staffing Plc T/A Guidant Global, Building Research Establishment, Placecube, Pixie Energy, Opinion Research Services, Comensura, and Constellia, including added rows and rows renamed to or from those names. Also Data Cubed Ltd, Gloucestershire County Council, Graham Tate T/A Exceptional Development, Grant Thornton, Grant Thornton UK LLP, HMRC, ICO, South Gloucestershire Council, Spark South West, University of Bath, University of the West of England, and WSP UK Limited.",
            "mixed",
            is_missed_publishing,
            None,
        ),
        (
            "individual-1",
            "Indidividual 1",
            "Payments to Y E Elsorougi, including added payments, payments un-redacted from Redacted - Sole Trader, and payments whose corrected supplier is a redaction of that name.",
            "mixed",
            is_individual_1,
            None,
        ),
        (
            "transport-renames",
            "Transport renames",
            "Already published payments renamed to C T Coaches Ltd, from Redacted - Sole Trader, C T Coaches (Susan Young & David Young T/A), or C T Coaches, payments renamed from The Big Lemon to Big Lemon Bristol and The West LTD, payments renamed from Eurotaxis Ltd to Eurocoaches Ltd, payments renamed from Faresaver Buses to Faresaver Ltd, the payment renamed from Turners Coachways Ltd to Turners Coachways (Bristol) Ltd, and payments renamed from Click Travel Ltd to Perk UK Ltd. New payments to these suppliers stay in Transport operators.",
            "changed",
            is_transport_rename,
            None,
        ),
        (
            "atkins-realis",
            "AtkinsRéalis",
            "Payments to Atkins Limited or AtkinsRéalis UK Limited. Added rows are new payments. Changed rows are the same payment with the supplier name updated, including where the accent in Réalis was stored as a different character. Farrelly Atkinson is not included.",
            "mixed",
            is_atkins,
            None,
        ),
        (
            "core-funding-monthly",
            "Core Funding monthly payments",
            "Added Core Funding payments described as Government Departments. These are the repeating payments to Bristol City Council.",
            "added",
            is_core_monthly,
            "Core Funding",
        ),
        (
            "central-government-monthly",
            "Central government monthly payments",
            "Added Funding from Central Government payments described as Government Departments, paid to Bristol City Council or to the Ministry of Housing, Communities and Local Government.",
            "added",
            is_central_monthly,
            "Funding from Central Government",
        ),
        (
            "capital-grants",
            "Capital grants",
            "Added payments described as Capital Grants, mostly to the councils, colleges, and energy companies. Also the eight Agencies or Public Bodies payments to the Department for Business, Energy and Industrial Strategy, the Department for Energy Security and Net Zero, and the Cabinet Office. Agency staff costs are not included.",
            "added",
            is_capital_grant,
            None,
        ),
        (
            "grants",
            "Grants",
            "Added payments whose purpose is Grants. Most of the money is Employment and Skills, paid to the colleges and the councils. This is separate from Capital Grants.",
            "added",
            lambda row: is_added_purpose(row, "Grants"),
            None,
        ),
        (
            "transport-operators",
            "Transport operators",
            "Added payments whose purpose is Transport Operators, almost all in Integrated Transport. First West of England Ltd is the largest recipient.",
            "added",
            is_transport_operator,
            None,
        ),
        (
            "other-local-authorities",
            "Other local authorities",
            "Added payments whose purpose is Other Local Authorities, mostly to Bath and North East Somerset, South Gloucestershire, Bristol, and North Somerset.",
            "added",
            lambda row: is_added_purpose(row, "Other Local Authorities"),
            None,
        ),
        (
            "professional-fees-project",
            "Professional fees project",
            "Added payments whose purpose is Professional Fees Project. Network Rail is most of the total, then WSP.",
            "added",
            lambda row: is_added_purpose(row, "Professional Fees Project"),
            None,
        ),
        (
            "payments-to-others",
            "Payments to others",
            "Added payments whose purpose is Payments to Others, almost all to the three councils.",
            "added",
            lambda row: is_added_purpose(row, "Payments to Others"),
            None,
        ),
        (
            "closed-supplier-rename",
            "Supplier name changes",
            "Changes where the supplier name was changed, but those payments do not appear to be connected with many other added payments.",
            "changed",
            is_closed_rename,
            None,
        ),
        (
            "redacted-supplier",
            "Redacted supplier",
            "An already published payment whose corrected supplier is a redaction, or where the original supplier name was a redaction. Payments that appear only in the corrected file are not included.",
            "redacted",
            is_redacted_supplier,
            None,
        ),
    ]
    claimed: set[int] = set()
    groups = []
    for group_id, title, note, kind, rule, baseline_area in rules:
        members = []
        added_amount = Decimal("0")
        changed_amount = Decimal("0")
        removed_amount = Decimal("0")
        for index, row in enumerate(rows):
            if index in claimed or not rule(row):
                continue
            claimed.add(index)
            row["group"] = group_id
            members.append(member(row))
            value = Decimal(row["amount"])
            if row["kind"] == "added":
                added_amount += value
            elif row["kind"] == "changed":
                changed_amount += value
            elif row["kind"] == "removed":
                removed_amount += value
        amount = added_amount + changed_amount + removed_amount
        if baseline_area:
            base = already_published(baseline_area)
            percent_note = f"The change is this group's total divided by the {pounds(base)} already published under {baseline_area}."
            percent = (amount / base * 100) if base else Decimal("0")
        elif group_id == "closed-supplier-rename":
            percent_note = "The payment amount did not change. Only the supplier name did."
            percent = Decimal("0")
        else:
            percent_note = ""
            percent = Decimal("0")
        groups.append(
            {
                "id": group_id,
                "title": title,
                "note": note,
                "kind": kind,
                "count": len(members),
                "amount": money(amount),
                "added_amount": money(added_amount),
                "changed_amount": money(changed_amount),
                "removed_amount": money(removed_amount),
                "percent": f"{percent:.1f}",
                "percent_note": percent_note,
                "members": members,
            }
        )
    for index, row in enumerate(rows):
        if index not in claimed:
            row["group"] = ""
    return groups, rows


def write_groups(groups: list[dict], rows: list[dict]) -> None:
    """Write one JSON file per group and groups/index.json."""
    GROUPS.mkdir(parents=True, exist_ok=True)
    index_groups = []
    for group in groups:
        payload = {
            "id": group["id"],
            "title": group["title"],
            "note": group["note"],
            "kind": group["kind"],
            "members": group["members"],
        }
        (GROUPS / f"{group['id']}.json").write_text(json.dumps(payload, indent=2))
        index_groups.append({key: group[key] for key in ("id", "title", "note", "kind", "count", "amount", "added_amount", "changed_amount", "removed_amount", "percent", "percent_note")})
    unassigned = [row for row in rows if not row["group"]]
    unassigned_amount = sum((Decimal(row["amount"]) for row in unassigned), Decimal("0"))
    index = {
        "unassigned_count": len(unassigned),
        "unassigned_amount": money(unassigned_amount),
        "groups": index_groups,
    }
    (GROUPS / "index.json").write_text(json.dumps(index, indent=2))
    print(f"unassigned {len(unassigned)} {unassigned_amount}")
    for group in index_groups:
        print(group["id"], group["count"], group["amount"], group["percent"] + "%")


def write_report(groups: list[dict], rows: list[dict]) -> None:
    """Write report/groups.html with the group controls and the payment table."""
    unassigned = [row for row in rows if not row["group"]]
    unassigned_amount = sum((Decimal(row["amount"]) for row in unassigned), Decimal("0"))
    total_amount = sum((Decimal(row["amount"]) for row in rows), Decimal("0"))
    assigned_amount = total_amount - unassigned_amount
    data = {
        "assigned_count": len(rows) - len(unassigned),
        "total_count": len(rows),
        "assigned_amount": float(assigned_amount),
        "total_amount": float(total_amount),
        "unassigned_count": len(unassigned),
        "unassigned_amount": float(unassigned_amount),
        "groups": [
            {
                "id": group["id"],
                "title": group["title"],
                "note": group["note"],
                "count": group["count"],
                "amount": float(group["amount"]),
                "added_amount": float(group["added_amount"]),
                "changed_amount": float(group["changed_amount"]),
                "removed_amount": float(group["removed_amount"]),
                "percent": group["percent"],
                "percent_note": group["percent_note"],
            }
            for group in groups
        ],
        "rows": rows,
    }
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(html)
    print(REPORT, REPORT.stat().st_size)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Correction groups</title>
<link rel="stylesheet" href="groups.css">
</head>
<body>
<main>
  <h1>Correction groups</h1>
  <p>Republished quarters only, and only payments that differ between the original and corrected files. A payment is in one group or in none.</p>
  <table class="summary" id="summary"></table>
  <div id="groups"></div>
  <p><button type="button" id="show-all" hidden>Show all</button> <button type="button" id="show-ungrouped">Show all ungrouped</button></p>
  <p id="txn-filters">
    <button type="button" data-txn="400008674">400008674</button>
    <button type="button" data-txn="400008810">400008810</button>
    <button type="button" data-txn="400008885">400008885</button>
    <button type="button" data-supplier="mhclg">MHCLG</button>
  </p>
  <p id="showing"></p>
  <div class="wrap">
    <table>
      <thead>
        <tr>
          <th data-key="kind">Change</th>
          <th data-key="date">Date</th>
          <th data-key="transaction_no">Transaction</th>
          <th data-key="supplier">Supplier</th>
          <th data-key="purpose">Purpose</th>
          <th data-key="service_area">Service area</th>
          <th class="num" data-key="amount" data-type="number">Amount</th>
          <th data-key="group">Group</th>
        </tr>
      </thead>
      <tbody id="body"></tbody>
    </table>
  </div>
</main>
<dialog id="info-dialog">
  <h2></h2>
  <p></p>
  <form method="dialog"><button type="submit">Close</button></form>
</dialog>
<script>
const DATA = __DATA__;
const POUNDS = new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 });
function money(value) {
  const amount = Math.round(Number(value));
  const sign = amount < 0 ? "-" : "";
  const abs = Math.abs(amount);
  if (abs > 1000000) return sign + "£" + (abs / 1000000).toFixed(1) + " million";
  return sign + POUNDS.format(abs);
}
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const titleOf = (id) => (DATA.groups.find((group) => group.id === id) || {}).title || "Unassigned";
const hidden = new Set(DATA.groups.map((group) => group.id));
let only = "";
let txn = "";
let supplier = "";
let sortKey = "amount";
let sortDir = -1;

document.getElementById("summary").innerHTML =
  `<tbody>
    <tr><th>Payments</th><td>${DATA.assigned_count} / ${DATA.total_count}</td></tr>
    <tr><th>Value</th><td>${money(DATA.assigned_amount)} / ${money(DATA.total_amount)}</td></tr>
    <tr><th>Value percentage</th><td>${(DATA.assigned_amount / DATA.total_amount * 100).toFixed(1)}%</td></tr>
  </tbody>`;

const host = document.getElementById("groups");
for (const group of DATA.groups) {
  const block = document.createElement("section");
  block.className = "group";
  block.dataset.group = group.id;
  block.innerHTML = `<button type="button" class="group-name" data-only="${esc(group.id)}">${esc(group.title)}</button>
    <table class="nums">
      <tr><th>Payments</th><td>${group.count}</td></tr>
      <tr><th>Value added</th><td>${money(group.added_amount)}</td></tr>
      <tr><th>Value changed</th><td>${money(group.changed_amount)}</td></tr>
      ${Number(group.removed_amount) ? `<tr><th>Value removed</th><td>${money(group.removed_amount)}</td></tr>` : ""}
      <tr><th>Change</th><td>+${esc(group.percent)}%</td></tr>
    </table>
    <div class="actions">
      <button type="button" data-info="${esc(group.id)}" title="Info">?</button>
      <button type="button" data-only="${esc(group.id)}">Show</button>
    </div>`;
  host.appendChild(block);
}

function isMinistry(row) {
  const blob = `${row.supplier || ""} ${row.original_supplier || ""}`.toUpperCase();
  return blob.includes("MHCLG") || blob.includes("MINISTRY OF HOUSING");
}

function visible(row) {
  if (txn) return row.transaction_no === txn;
  if (supplier === "mhclg") return isMinistry(row);
  const group = row.group || "";
  if (group && hidden.has(group)) return false;
  if (only) return group === only;
  return true;
}

function draw() {
  const rows = DATA.rows.filter(visible).slice().sort((a, b) => {
    const av = sortKey === "amount" ? Number(a[sortKey]) : a[sortKey];
    const bv = sortKey === "amount" ? Number(b[sortKey]) : b[sortKey];
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
    return String(av).localeCompare(String(bv), "en", { numeric: true }) * sortDir;
  });
  const kindLabel = { added: "Added", removed: "Removed", changed: "Changed" };
  function sideBySide(before, after) {
    if (before && before !== after) {
      return `<span class="before">${esc(before)}</span><span class="after">${esc(after)}</span>`;
    }
    return esc(after || "");
  }
  function amountCell(row) {
    const after = money(Number(row.amount));
    if (row.kind === "changed" && row.original_amount && row.original_amount !== row.amount) {
      return `<span class="before">${money(Number(row.original_amount))}</span><span class="after">${after}</span>`;
    }
    return after;
  }
  document.getElementById("body").innerHTML = rows.map((row) => `<tr class="${esc(row.kind)}">
    <td class="kind">${esc(kindLabel[row.kind] || row.kind)}</td>
    <td>${esc(row.date)}</td>
    <td>${esc(row.transaction_no)}</td>
    <td>${sideBySide(row.original_supplier, row.supplier)}</td>
    <td>${sideBySide(row.original_purpose, row.purpose)}</td>
    <td>${sideBySide(row.original_service_area, row.service_area)}</td>
    <td class="num">${amountCell(row)}</td>
    <td>${esc(titleOf(row.group))}</td>
  </tr>`).join("");
  document.querySelectorAll(".wrap th").forEach((th) => {
    const mark = th.dataset.key === sortKey ? (sortDir < 0 ? " ↓" : " ↑") : "";
    th.textContent = th.dataset.label + mark;
  });
  document.querySelectorAll(".group").forEach((card) => {
    card.classList.toggle("on", only === card.dataset.group);
  });
  document.querySelectorAll("[data-txn]").forEach((button) => {
    button.classList.toggle("on", txn === button.dataset.txn);
  });
  document.querySelectorAll("[data-supplier]").forEach((button) => {
    button.classList.toggle("on", supplier === button.dataset.supplier);
  });
  const total = rows.reduce((sum, row) => sum + Number(row.amount), 0);
  const value = `${rows.length.toLocaleString("en-GB")} payments, ${money(total)}`;
  let showing;
  function beforeAndAfter(list) {
    let before = 0;
    let after = 0;
    for (const row of list) {
      if (row.kind === "removed") before += Number(row.amount);
      else if (row.kind === "changed") {
        before += Number(row.original_amount);
        after += Number(row.amount);
      } else after += Number(row.amount);
    }
    return `Before ${money(before)}, new ${money(after)}, difference ${money(after - before)}.`;
  }
  if (txn) {
    showing = `Showing transactions with number ${txn}. ${beforeAndAfter(rows)}`;
  } else if (supplier === "mhclg") {
    showing = `Showing payments to the Ministry of Housing, Communities and Local Government or MHCLG. ${beforeAndAfter(rows)}`;
  } else if (only) {
    showing = `Showing only ${titleOf(only)}: ${value}.`;
  } else {
    const shown = DATA.groups.filter((group) => !hidden.has(group.id));
    const concealed = DATA.groups.filter((group) => hidden.has(group.id));
    if (concealed.length === 0) {
      showing = `Showing every differing payment, including those in no group: ${value}.`;
    } else if (shown.length === 0) {
      showing = `Showing payments that are in no group. ${value}.`;
    } else {
      const names = shown.map((group) => group.title).join(", ");
      showing = `Showing payments in no group, plus ${names}. ${concealed.length} groups are hidden. ${value}.`;
    }
  }
  document.getElementById("showing").textContent = showing;
  document.getElementById("show-all").hidden = !only && !txn && !supplier;
}

document.querySelectorAll(".wrap th").forEach((th) => {
  th.dataset.label = th.textContent;
  th.addEventListener("click", () => {
    if (sortKey === th.dataset.key) sortDir = -sortDir;
    else { sortKey = th.dataset.key; sortDir = th.dataset.type === "number" ? -1 : 1; }
    draw();
  });
});
host.addEventListener("click", (event) => {
  const info = event.target.dataset && event.target.dataset.info;
  const onlyId = event.target.dataset && event.target.dataset.only;
  if (info) {
    const group = DATA.groups.find((item) => item.id === info);
    const dialog = document.getElementById("info-dialog");
    dialog.querySelector("h2").textContent = group.title;
    dialog.querySelector("p").textContent = [group.note, group.percent_note].filter(Boolean).join(" ");
    dialog.showModal();
    return;
  }
  if (onlyId) {
    only = only === onlyId ? "" : onlyId;
    txn = "";
    supplier = "";
    if (only) hidden.delete(only);
    draw();
  }
});
document.getElementById("txn-filters").addEventListener("click", (event) => {
  const nextTxn = event.target.dataset && event.target.dataset.txn;
  const nextSupplier = event.target.dataset && event.target.dataset.supplier;
  if (nextTxn) {
    txn = txn === nextTxn ? "" : nextTxn;
    supplier = "";
    only = "";
    draw();
  }
  if (nextSupplier) {
    supplier = supplier === nextSupplier ? "" : nextSupplier;
    txn = "";
    only = "";
    draw();
  }
});
document.getElementById("show-all").addEventListener("click", () => {
  hidden.clear();
  only = "";
  txn = "";
  supplier = "";
  draw();
});
document.getElementById("show-ungrouped").addEventListener("click", () => {
  DATA.groups.forEach((group) => hidden.add(group.id));
  only = "";
  txn = "";
  supplier = "";
  draw();
});
document.getElementById("info-dialog").addEventListener("click", (event) => {
  if (event.target.tagName === "DIALOG") event.target.close();
});
draw();
</script>
</body>
</html>
"""


def main() -> None:
    rows = load_diff("added") + load_diff("removed") + load_diff("changed")
    groups, rows = assign(rows)
    write_groups(groups, rows)
    write_report(groups, rows)


if __name__ == "__main__":
    main()
