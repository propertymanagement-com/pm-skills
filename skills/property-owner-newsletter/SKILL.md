---
name: property-owner-newsletter
version: 0.1.0
description: Build the monthly, owner-specific "Property Owner Update" email package for a property management company from AppFolio report exports, the PropertyManagement.com connector (owner survey results) and verified-PM benchmarks. Produces a mail-merge file, rendered previews, a portfolio report page per owner, and a review studio where the comms lead can preview any owner's email and edit its fields before sending. Use this whenever the user mentions the owner newsletter, owner update, monthly owner email, portfolio report for owners, mail merge to owners, "what do we send owners this month", or wants to review or change one owner's personalized email, even if they never say "newsletter".
---

# Property Owner Newsletter

One email a month to every active property owner, about **their** homes: the numbers, what is coming up, what the company changed, and how they compare against verified property managers. Same template for everyone, different data in every copy. The company's comms lead reviews and sends it with their own mail-merge tool; this skill never sends anything.

Why owner-specific: a generic newsletter gets skimmed.

## Version handshake (every run)

Call **`pm_skill_hello`** with `{ "skill": "property-owner-newsletter", "version": "0.1.0" }` before other work. If `is_latest` is false, mention once that a newer release exists; do not repeat in the same conversation. An email that says "your home at 421 W Elm St, leased at $1,850, lease ends Nov 30, we recommend renewing flat" gets read and replied to. Replies are the point: every reply is a retention conversation the company would otherwise never have.

## Before anything: permissions and files

- When the PropertyManagement.com connector is added, tell the person to choose **Allow always** (the connector is read-only). Otherwise every run re-asks, and a nervous "don't allow" stops the skill mid-way.
- Keep the export folder inside the Claude workspace (a Project, or files added to the conversation) rather than on the desktop, so Claude is not asking for desktop access during the run. When a file prompt still appears, say in one line what it is for and which button to press.
- Never show raw JSON or script output in the reply. Scripts print one plain line and write their detail to files; read the files.

## What comes out

Everything lands in `<out>/newsletter/`:

| File | What it is | Who uses it |
|---|---|---|
| `merge.csv` / `merge.json` | one row per eligible inbox, every merge field filled (numbers, paragraphs, report link); text only, so any merge tool can use it | the mail-merge tool |
| `email-template.html` / `.txt` | the plain templates with `{{tokens}}`, paste into the merge tool | the mail-merge tool |
| `merge-visual.csv` + `email-template-visual.html` | the same rows plus three HTML snippet columns (`homes_rows`, `occupancy_cells`, `compare_bars`: per-property rows with status chips, a cell per unit, comparison bars, all table-based so they render in Outlook and Gmail) and the template that uses them. Use these when the sending tool passes HTML through per recipient (Mailchimp, HubSpot, SendGrid, Resend); the previews and the studio show this version | the mail-merge tool |
| `previews/*.html` | six rendered emails covering the main cases (one quiet home, largest owner, one with a `[CONFIRM]`, a promoter, a lease ending, a multi-property owner) | the comms lead, first look |
| `reports/<token>.html` | one portfolio report page per owner, built only when `newsletter.report_link` is true in the config (off in version one: the email then has no report button) | the company hosts this folder |
| `newsletter-studio.html` | owner picker with filters (needs a sentence / radar call-first / edited / no survey), a send-readiness bar, faithful preview, every field editable, export merge CSV/JSON | the comms lead, final review |

`references/merge-fields.md` explains every column. `references/studio-guide.md` is the walkthrough to hand the comms lead.

## What it needs

1. **AppFolio exports** in one folder, with the standard settings in `references/appfolio-exports.md`. Required for this skill: rent roll, property directory, owner directory, lease expiration detail, unit vacancy detail, charge detail (rent GL, Charge Status All, last 90 days), delinquency. Nice to have: unit directory, tenant tickler, lease history, renewal summary, work orders (they sharpen the report page and the comparisons; the run works without them).
2. **Owner survey results** through the PropertyManagement.com connector, saved as `survey.json` (schema and the exact tool calls are in `references/pmcom-connector.md`). Optional: without it the survey sentence is simply left out.
3. **The client config** at `assets/client-config.json`: company details, brand colours and fonts, the team, the referral line, the monthly company update, the recommendation rules, the certifications to feature, and the URL where the report pages will be hosted. Confirm the `[CONFIRM]` and `_confirm` items on the first run and they persist.

Never invent a number to fill a gap. If a report is missing, ask for it (step 2) and wait.

## First run: guided setup

The packaged `assets/client-config.json` is the starting point PropertyManagement.com prepared, and inside Claude the package is read-only. The member's own copy lives **in the folder that holds their monthly exports** (`<exports>/client-config.json`), next to `survey.json` and last month's outputs, so it persists from month to month and travels with the data. Always look there first; fall back to the packaged config only to create that copy.

On any run, before the work:

```bash
python3 scripts/setup_config.py init --from assets/client-config.json --to <exports>/client-config.json   # no-op once it exists
python3 scripts/setup_config.py status --config <exports>/client-config.json
```

If `setup_needed` is true (no `setup.completed_at`, or placeholders still open), run the setup conversation before anything else. It is short and it is the reason the outputs come out right, so do not skip it or bury it:

0. If the PropertyManagement.com connector is connected, call **`pm_org_get`**, save the JSON, and run `python3 scripts/setup_config.py seed --config <exports>/client-config.json --org-json <exports>/org.json` before the checklist. If the connector is missing, skip seeding and ask during the checklist.
1. Print the checklist (`setup_config.py checklist --config ...`) and ask **in one message**, grouped the way the checklist groups them (company, team and direct phones, brand, regions, newsletter host and lines, certifications, fees, risk thresholds), showing the current value for each so the person only has to correct what is wrong. Offer the defaults. Accept partial answers; whatever is not answered stays open and gets asked again next month, it never blocks the run.
2. Write the answers with `setup_config.py apply --config <exports>/client-config.json --answers answers.json` (or `--set path=value` for one or two fields) and `--by <name>`. It stamps `setup.completed_at` and reports what is still open.
3. Check the connector once: call `pm_ping`, `pm_truematch_survey_overview`, and **`pm_benchmarks_get`**. Write survey to `<exports>/survey.json` and benchmarks to `<exports>/benchmarks.json`. If the connector is not present, say so in one line and continue; the survey sentence and benchmark sentences are left out until it is added (Settings → Connectors → Add custom connector → paste the org URL from the PM.com Client Dashboard MCP page: `https://mcp.propertymanagement.com/api/mcp/v1/orgs/<org-id>`).
4. Then inventory the exports (next section). On the very first run the person often has none yet: give them the export list for this skill with the steps from `references/appfolio-exports.md`, and stop until the folder is filled.

From then on every command takes `--config <exports>/client-config.json`. Anything the person changes later (a new manager, a new phone, this month's company update) goes through `setup_config.py apply` so the file stays valid.

## Workflow

Run everything from the skill folder. `<exports>` is the folder of AppFolio files, `<out>` is a working folder for this month (for example `runs/2026-10`).

### 1. Confirm the month, then inventory the exports

Ask which month the email goes out (this is the label on the email and the start of the "coming up" horizon; the data can be a week or two older). Then:

```bash
python3 scripts/appfolio_loader.py inventory <exports>
```

It prints which reports were recognised, their as-of dates, and which required ones are missing.

### 2. Ask for anything missing, with the export steps

If a required report is missing or older than 45 days, stop and ask the user for it. Quote the export steps from `references/appfolio-exports.md` for that exact report (report name, filters, columns, date range, file format), so the person can pull it in two minutes without guessing. Do not proceed with a partial bundle: a newsletter built on a stale rent roll tells an owner the wrong thing about their own property, which is worse than no email.

### 3. Pull the survey results

Use the PropertyManagement.com connector as described in `references/pmcom-connector.md`: overview, then list responses, then each response, written to `<exports>/survey.json`. If the connector is not available, say so and continue without it.

### 4. Compute the features

```bash
python3 scripts/appfolio_loader.py features <exports> --out <out> --survey <exports>/survey.json --config <exports>/client-config.json
```

Read `<out>/data-quality.md` and relay anything that changes what the emails say (blank manager names, units with 0 days vacant, missing market rents).

### 5. Build the package

```bash
python3 scripts/build_newsletter.py --out <out> --config <exports>/client-config.json --benchmarks <exports>/benchmarks.json --month YYYY-MM
```

It prints one line and writes the detail to `newsletter/build-summary.json`: owners in the send, exclusions by reason, the mix of "coming up" items, how many rows still carry a `[CONFIRM]`, how many inboxes in the send held more than one owner record (merged into one email each; the loader's data-quality note counts merges across every owner including departed ones, so its number is larger), and whether the company update is still the placeholder. Read the file, not the terminal.

### 6. Review with the comms lead

Report back in this shape, then point them at the studio:

- **Send size**: N owners in, M excluded (management ended / end date set / no email / no active units).
- **Needs a human sentence**: the owners whose "coming up" carries `[CONFIRM]` (vacancies over 30 days, balances over a month of rent). Each needs the real plan typed in. List them by manager so the manager can answer in one pass.
- **Company update**: if `company_block` is still the placeholder, ask for two or three sentences on what changed this month and put them in the config (they carry into every row).
- **Merged inboxes**: AppFolio often holds one person as several owner records (a person plus their LLCs, or two records on one property). The builder sends one email per inbox covering every property; the studio lists the merges. Name them so the comms lead can confirm that matches how those owners want to hear from the company.
- **Call list overlap**: owners tagged `Call this week` by the Retention Radar (the studio shows the radar tier on each owner) should be called before the email lands, or held out of this send. Say who they are.
- **Studio**: open `newsletter-studio.html`, pick an owner, edit any field, watch the preview update, export the merge CSV when done. Edits live in the page until exported, so export before closing.

### 7. Host the report pages and send

- If `report_link` is on: upload `<out>/newsletter/reports/` to the host behind `report_base_url` (any static host works). The file names are unguessable tokens, stable month to month for the same owner. In version one the link is off and this step is skipped.
- Import the exported merge CSV and the template into the mail-merge tool the company already uses (Gmail with YAMM or Mail Merge, Mailchimp, HubSpot, Constant Contact). Send one test to the comms lead first. They press send.

## Present it

- **claude.ai (Team or Enterprise):** before writing anything else, read one preview (about 17 KB) and return it as an HTML artifact so the first thing on screen is the email exactly as an owner will see it; offer the other previews the same way. Never paste JSON or code into the reply. The studio embeds every owner (about 1.7 MB) and is a working tool, not a page to read, so it stays a file: point to `newsletter-studio.html` and explain that it opens in any browser. Artifacts can be shared to teammates in the workspace; the report pages are hosted by the company, never as public artifacts.
- **Claude desktop / Claude Code:** open the studio directly.

Everything here carries owner names and addresses. Share inside the company only.

## Rules that hold every run

- **Owner-specific only.** Every sentence about a property is about that owner's property. Never put another owner's address, name or numbers in a row. The report link carries no name, only the token.
- **Survey answers stay confidential.** The survey band (promoter / passive / detractor) is used only to order the preview list and to flag the radar overlap. Never quote or reference an owner's survey answer in their email, and never tell one owner what another said.
- **`[CONFIRM]` never ships.** Any row still containing `[CONFIRM` after review is held back. The builder flags them; the studio shows them; the send must not include them.
- **One email per inbox.** Never two copies to the same address in one send; the merge step handles it, do not undo it by hand.
- **One version for everyone.** Do not fork the template by segment. Personalisation comes from the data, not from different letters.
- **Numbers come from the exports and the connector.** No estimates, no rounding a vacancy down, no "about". If a value is missing it renders as `n/a` with an honest label.
- **Benchmarks change the sentence or they are left out.** The comparison section cites verified-PM medians from **`pm_benchmarks_get`** (saved to `benchmarks.json`, passed as `--benchmarks`) only where the company's number is in the same conversation; quote **n** and **as_of**. If benchmarks are unavailable, omit those sentences rather than inventing numbers. The config's `compare` block decides which metrics may appear (renewals only when within 5 points of the median by default).
- **Voice**: plain, specific, no marketing filler. `references/writing-rules.md` applies to every sentence the studio user might edit, and to any copy you draft for the company update.
- **Never send.** Not from the skill, not from a connector. The comms lead sends from their own tool after the test email.

## Answering questions about the send

When the question is about one owner ("show me Dan's email", "what will the Testville building's update say"), the answer names that owner only. Everything else in the send is a count ("30 other rows still need a sentence, listed in the studio"), never a roster: a person asking about one owner did not ask to see the others, and a list of names in a reply travels further than the studio does.

Once `merge.json` exists you can answer directly from it: "which owners have a vacancy over 30 days" (rows whose `coming_up` starts with a vacancy sentence), "who is getting a renewal recommendation" (`lease at your` in `coming_up`), "how many owners are under Carlos" (`manager_first`), "show me Bonnie's email" (open her preview or render the template with her row). For anything about why a number is what it is, `references/metric-definitions.md` has the definitions and `references/data-model.md` the fields.

## Changing behaviour

- Recommendation stances (renew flat, propose an increase, cap at 5%) live in `assets/client-config.json` under `newsletter.recommendation_rules` and `max_increase_pct`; the logic that applies them is in `scripts/build_newsletter.py` `recommendations()`. `references/recommendation-rules.md` lists every rule with the sentence it produces.
- Which comparisons may appear: `newsletter.compare`. Featured certifications: `newsletter.certifications_to_feature` (pull the values from the company's PropertyManagement.com profile each quarter).
- Exclusions: `exclusions` (management end date set, no email). Departed owners are always excluded.
- Brand colours, fonts, logo: `brand` and `company.logo_url`. The template is `assets/email-template.html`; keep the `{{tokens}}` if you restyle it.
