# How the groups page is built

`report/groups.html` is the page for inspecting payments that differ between an original West of England Combined Authority transparency report and the corrected report that replaced it. Styling is in `report/groups.css`. The page is generated. Edit the scripts, then rebuild. Do not hand-edit the HTML: the next rebuild overwrites it.

## Recreate everything

From the project root, with the downloaded files already in `source/`:

```bash
.venv/bin/python scripts/build_spend.py
python3 scripts/assign_groups.py
```

`scripts/build_spend.py` needs the project virtualenv because it reads Excel workbooks with openpyxl. `scripts/assign_groups.py` uses only the Python standard library. Running `assign_groups.py` again is enough to recreate the groups and the HTML from the diff files already in `data/diffs/`.

## Step 1: normalise and compare

`scripts/build_spend.py` reads the quarterly spend CSV and spreadsheet files under `source/uploads/`. It uses `source/download-results.json` to know which file is which quarter, and whether it is the corrected report, the original, or the only published file.

It writes:

- `data/transactions.csv` — one row per payment, with `financial_year`, `quarter`, and `version` (`corrected`, `original`, or `only`).
- `data/summary_by_file.csv` and `data/summary_by_year.csv` — totals and date spans. A year total uses the corrected file when one exists, so a quarter is not counted twice.
- `data/diffs/all-added.csv` — payments only in the corrected report.
- `data/diffs/all-removed.csv` — payments only in the original report.
- `data/diffs/all-changed.csv` — payments in both, with original and corrected values side by side.
- `data/diff_summary.csv` — one row per republished quarter.

The comparison covers the 22 republished quarters, 2020/21 Q1 through 2025/26 Q2. A row matches when transaction number, amount, date, and supplier agree. Transaction numbers are not unique, so leftovers are then paired on transaction number alone. That second step can place two different payments next to each other when they share a number. `all-changed.csv` should be read with that in mind.

## Step 2: assign groups and write the page

`scripts/assign_groups.py` reads the three combined diff files. Each payment becomes one display row. For a changed payment, the visible supplier, purpose, service area, date, and amount come from the corrected report. The original values are kept so the table can show them struck through.

The rules in `assign()` run in order. The first match wins, so a payment is in one group or in none. Named suppliers and other specific groups are listed before generic ones, such as a purpose, a CLOSED prefix, or a redaction.

1. **Missed publishing** (`missed-publishing`). Payments omitted from the originally published reports. Includes Felinesoft Ltd, both added payments to CLOSED Clearcourse Membership Services Ltd (Felinesoft) and changed payments renamed to that name, AECOM payments that were added or removed, payments to North Somerset Council, payments to Avon Pension Fund, and payments to Bath & North East Somerset Council General Suspense Account, including the published payment renamed to Bristol City Council. There are no changed AECOM payments in the diff. North Somerset Enterprise Agency is not included. Also Carlisle Staffing Plc T/A Guidant Global, Building Research Establishment, Placecube, Pixie Energy, Opinion Research Services, Comensura, and Constellia, including added rows and rows renamed to or from those names. Also Data Cubed Ltd, Gloucestershire County Council, Graham Tate T/A Exceptional Development, Grant Thornton, Grant Thornton UK LLP, HMRC, ICO, South Gloucestershire Council, Spark South West, University of Bath, University of the West of England, and WSP UK Limited.
2. **Indidividual 1** (`individual-1`). Payments whose original or corrected supplier is Y E Elsorougi. That includes added payments, un-redactions from Redacted - Sole Trader, and payments later redacted from that name.
3. **Transport renames** (`transport-renames`). Changed payments renamed to C T Coaches Ltd, changed payments renamed from The Big Lemon to Big Lemon Bristol and The West LTD, changed payments renamed from Eurotaxis Ltd to Eurocoaches Ltd, changed payments renamed from Faresaver Buses to Faresaver Ltd, the payment renamed from Turners Coachways Ltd to Turners Coachways (Bristol) Ltd, and changed payments renamed from Click Travel Ltd to Perk UK Ltd. Added payments to these suppliers stay in Transport operators.
4. **AtkinsRéalis** (`atkins-realis`). Added payments to AtkinsRéalis UK Limited, and changed payments renamed from Atkins Limited or between spellings of AtkinsRéalis. Farrelly Atkinson is not included.
5. **Core Funding monthly payments** (`core-funding-monthly`). Added payments in service area Core Funding, purpose Government Departments.
6. **Central government monthly payments** (`central-government-monthly`). Added payments in service area Funding from Central Government, purpose Government Departments, paid to Bristol City Council or to the Ministry of Housing, Communities and Local Government.
7. **Capital grants** (`capital-grants`). Added payments whose purpose is Capital Grants, plus added payments whose purpose is Agencies or Public Bodies. Agency staff costs are not included.
8. **Grants** (`grants`). Added payments whose purpose is Grants. Separate from Capital Grants. Most of the money is Employment and Skills, paid to the colleges and the councils.
9. **Transport operators** (`transport-operators`). Added payments whose purpose is Transport Operators, almost all in Integrated Transport.
10. **Other local authorities** (`other-local-authorities`). Added payments whose purpose is Other Local Authorities.
11. **Professional fees project** (`professional-fees-project`). Added payments whose purpose is Professional Fees Project.
12. **Payments to others** (`payments-to-others`). Added payments whose purpose is Payments to Others.
13. **Supplier name changes** (`closed-supplier-rename`). Changed payments whose corrected supplier starts with `CLOSED` and, after that word is removed, matches the original name. A shortened name still matches. Also named un-redactions to Graham Tate, Jean Vernon, and The Bristol Bike Project, and the renames for Altonian Coaches, Bristol Community Energy, Rowe IT to CACI, Socitm Advisory to Civiteq, Future Leap, The Prince's Trust, Destination Bristol T/A Visit West, PEC Trust, 11KBW (JG QC to KC), Clear Review, Avin Electronics, Bristol Payji, Bristol Green Capital Partnership, HCT Group, Waller and Wood, A D Young Technical Services, CSquared acting for WECA, and further spelling, trading-name, and legal-name updates including Knowle West Media Centre, Anatomy Studio, Squarebird, PK Group, Economic Modelling, Solace in Business, Team Telemarketing, Pytch, SS Great Britain Trading, Destination Bristol, Mayden House, Jekka's, St Helen's Church, Kate's Kitchen, Suited and Booted, CH2M Hill, Spark South West, Somerset County Council, 11KBW, Bristol Music Trust, the Centre for Public Scrutiny, Chew Valley Gates, the Coal Authority, Elior, Women's Work Lab, Diverse Artists Network, creativeShift, Ecuity Advisory, Bristol Spaceworks, Cabinet Office, Bath Property Maintenance, the Robotics Network, Objective, St Brendan's, CSquared day-to-day management, DTW, EAL Inclusive, EAV Solutions, Mazars, Fowlers of Bristol, Global Radio, John Wesley's New Room, Kelp Industries, Farm.ink, WPD Telecoms, RWK Goodman, Evelyn Partnership, Safer Shops, Valleys Waste Services, The Somerset Toiletry, Sustrans, Staplebarn, Momentum Scooters, Rymar Services, Clifton Photonics, Sassy Scents, Counter Culture Drinks, Smarter Shows, Truple Co Roast, Renn Consultancy, The Social Detail, Oasis Academy Brislington, Contrast Timbers, Constellia, Formadome, Independent Composites, Digital Advisory Services, The Agency Global, Prism, The Conservative Volunteers, Reed Business Information, and Omnigenix.
14. **Redacted supplier** (`redacted-supplier`). Changed payments whose corrected supplier contains “redact”, including `[REDACTED]` and `Redacted - Sole Trader`. Also un-redactions from Redacted - Sole Trader to CLOSED names for Cirque Bijou, Calyo, Auroch Digital, Bill Sharpe Research, Andre Pattenden, Zlati Spasova Art, Victoria Bourne, Adam Gasson, Anna Barclay, Avon Wildlife Trust, Bath City Farm, Briony Phillips, Buckman Associates, Bo Lanyon Studio, Hex Productions, Jessica Thorn Ceramics, Kings Chambers, Katy Welsh, Made My Wardrobe, W Hobbs Window Cleaning, Harry Cobbold, Mayk Theatre, Mr A J Richards, Ms D J Robinson, N Al-Tahhan, Freia Turland, Jonesmillbank, NGD Advisory Services, Roz Stewart-Hall, ProjICT, Colm Watling, Ali Hadavizadeh, Flint Innovation, Laura Williams, Elected Technologies, Phil Chamberlain, The Presentation Maestro, Francis Taylor Building, Gerard Liston, Cognitive Paths, Diva Agency, Centre for Sustainable Energy, Carruthers Tanner, Bristol Jazz and Blues Festival, Centre for Cities, Creativity Works, Deloitte MCS, Ester de Roij, Great Copy Matters, Andy Council, Anna Smithson, Clare Diston, Colin King, Katy Connor, Jessica Augarde, Jon Aitken, Moore, the National Centre for Integrative Medicine, Raucous, the Green Register, Carmel Bristol, Daniel Wood Associates, Petroc, Frazer Meaking, Hawkesbury Volunteer Transport Group, Leonard Cheshire, Ruth Gerrard, Spark Films, Sprint Print & Design, The Musuem of East Asian Art, Tim Scoones, A J Belshaw, Nick Young, Arima Consulting, Atomic Smash, Next Venture Studio, The Invisible Circus, Chris Hackett, Esther Shelley Design, Marshfield Community Land Trust, Paul Gillis, The Crafty Hen, Landor Links, and Redcatch Community Garden. Added payments are not included, even when the new row is already labelled redacted. Named groups listed above still win when they match the same payment.

The script writes:

- `groups/<id>.json` — the payments in that group.
- `groups/index.json` — counts, amounts, and notes.
- `report/groups.html` — the summary, the group cards, and the payment table.

The HTML links to `report/groups.css`. Change type sizes and colours there. Reload the page. A rebuild does not overwrite the CSS file.

The table lists every differing payment, including those in no group. The Change column is Added, Removed, or Changed. On a changed row, the original text is struck through and the corrected text is shown underneath.
