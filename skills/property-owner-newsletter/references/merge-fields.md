# Merge fields

Every column in `merge.csv` (and every key in `merge.json` rows). The template references them as `{{field}}`. Fields marked **editable** are the ones the studio exposes; the rest are identity, brand or bookkeeping.

## Identity and routing

| Field | Meaning | Editable |
|---|---|---|
| `owner_id` | AppFolio owner ID (from the owner directory); `123+456` when several owner records sharing one inbox were merged into one email | no |
| `email` | first email on the owner directory row; the send address | yes |
| `first_name` | owner's first name, `there` when the directory has none (renders "Hi there,") | yes |
| `owner_name` | full owner name (a person or an LLC); `A / B` for a merged inbox | no |
| `manager_first` / `manager_name` / `manager_phone` | the site manager on the owner's first property, from the property directory's Site Manager Name matched to `team.managers` in the config; `our team` and the company phone when blank | yes |
| `month` / `month_label` | `2026-10` / `October 2026`, the send month | no |
| `home_word` / `home_word_upper` | `home` (one single-unit property), `building` (one multi-unit), `homes` (several single-family), `properties` (mixed) | no |
| `properties_count` / `units` / `occupied` | portfolio size from the rent roll, active properties only | no |

## Copy

| Field | What the builder puts there | Editable |
|---|---|---|
| `subject` | "Jane, your October 2026 property update from Example PM" ("Your ..." when no first name) | yes |
| `preheader` | "3 of 4 leased, 84% of rent collected, and what is coming up." | yes |
| `intro_line` | one sentence framing the email | yes |
| `homes_paragraph` | one property: "Your single-family home at 100 Example St in Testville: leased at $1,850/mo, in line with market, with us since Aug 2023." Several: "Your properties: 5-unit building at ... (4 of 5 units leased, $10,184/mo total, rents in line with market, with us since Oct 2023); ..." (first six, then "and N more") | yes |
| `coming_up` | up to two sentences from the recommendation rules (see `recommendation-rules.md`), or the quiet line: "No leases end in the next 90 days and nothing is vacant. Nothing you need to decide this month; Test will flag anything that changes." | yes |
| `company_block` | the monthly company update from the config, identical in every row | yes (per row) |
| `how_you_compare` | rent collected on this owner's homes vs the company vs the verified-PM median; the featured certifications; the owner-survey NPS vs all verified managers; renewals only when the company is within 5 points of the median | yes |
| `closing_line` | "Questions about your home? Reply to this email or call Test Manager at ..." | yes |
| `referral_line` | the soft referral ask from the config | yes |

## Numbers (tiles)

| Field | Value | Label field |
|---|---|---|
| `occupancy_txt` | "3 of 4" leased units today | `occupancy_label` |
| `collected_txt` | rent collected over the last 90 days, charge-weighted across the owner's properties, rent GL only; `n/a` when the owner has no leased units | `collected_label` |
| `rent_txt` | monthly rent on leased units | `rent_label` |
| `past_due_txt` | tenant balances past due today, floored at $0 (a credit balance shows as $0) | `past_due_label` |

## Links and brand

| Field | Meaning |
|---|---|
| `report_url` | `report_base_url` + `/` + `report_token` + `.html`; the token is a 16-character hash of the owner ID and the config's `report_salt`, stable across months |
| `report_button` / `report_line` | the HTML button and the plain-text line for the report page; both empty while `newsletter.report_link` is false (version one), so the email simply has no report link |
| `report_token` | the file name of this owner's report page in `reports/` |
| `profile_url` | the company's PropertyManagement.com profile |
| `company_name`, `company_phone`, `logo_url`, `brand_primary`, `brand_accent`, `font_display`, `font_body` | from the config |
| `as_of` | rent roll as-of date, printed in the footer |
| `benchmarks_as_of` | date of the verified-PM medians |
| `footer_note` | the one-line reason they are receiving the email |

## Internal (JSON only, never in the CSV)

`_needs_confirm` (a `[CONFIRM` is still in `coming_up`), `_radar_tier` (the Retention Radar tier for this owner, to hold back or call first), `_survey_band` (promoter / passive / detractor / no survey, used only to pick previews; never shown to the owner).

## Visual columns (`merge-visual.csv` only)

| Field | What it holds |
|---|---|
| `homes_rows` | a table with one row per property: address, the sub-line (leased at $X, in line with market, with us since), a cell per unit coloured by status, a status chip, the monthly rent |
| `occupancy_cells` | one small cell per unit across the whole portfolio (leased in the brand colour, grey between tenants, amber past 30 days vacant, red past 60, green pre-leased) |
| `compare_bars` | the "How you compare" bars: this owner's rent collected vs the company vs the verified-PM median |

They are HTML built from table cells with inline styles. Simple merge tools (Gmail add-ons) escape HTML in merge fields, which is why they live in a separate file; the plain `merge.csv` carries the same facts as text.
