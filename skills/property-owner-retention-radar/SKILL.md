---
name: property-owner-retention-radar
version: 0.1.0
description: Builds the Property Owner Retention Radar for a property management company from its AppFolio report exports plus PropertyManagement.com owner-survey responses and verified-PM benchmarks. One page that runs the renewal play, survey detractors and likely detractors paired with what is happening on their properties today and the next renewal inside 90 days, plus this week's five owners to reach with a win in hand, and a CSV for the task system. Use this whenever a property manager asks which property owners are at risk of leaving, wants a churn or retention view, asks "who should we reach this week", mentions owner churn, management terminations, owners selling, detractors, or wants to combine owner survey results with their AppFolio data. Also use it for monthly or on-demand re-runs and for "what changed since last time".
---

# Property Owner Retention Radar

You are building an operator's weekly page, not a report and not a CRM.

## Version handshake (every run)

Call **`pm_skill_hello`** with `{ "skill": "property-owner-retention-radar", "version": "0.1.0" }` before other work. If `is_latest` is false, mention once that a newer zip or marketplace release exists; do not repeat in the same conversation. The person running it is a company owner or a director of operations. The page tells them which property owners are unhappy or about to be, what is happening on those owners' properties right now, and the five people to reach this week with something positive in hand. Their team then does the work in the tools they already use. The play behind the page is in `references/renewal-play.md`; read it once.

## Before anything: permissions and files

Two things stop a first run cold, and both are avoidable:

- **Claude Team or Enterprise plans.** Custom connectors are added by a workspace admin (Settings, Connectors, Add custom connector, paste the URL from `company.mcp_connector_url`). Everyone else then hard-refreshes Claude before the connector shows up under their own Settings, Connectors; each person connects it with their own PM.com login, or the admin connects it once for the whole organization. When someone says they cannot see the connector, this is the first thing to check.
- **The connector permission dialog.** When the PropertyManagement.com connector is added, Claude asks how to handle its tools. Tell the person to choose **Allow always** (the connector is read-only). Otherwise every run re-asks, and a nervous "don't allow" stops the skill mid-way.
- **File access prompts.** If the exports sit on the desktop, Claude asks for permission to read them, sometimes more than once, and the prompts read like code to someone who has never seen them. Ask the person to keep the export folder inside their Claude workspace (a Project, or files added to the conversation) rather than on the desktop. When a prompt still appears, say in one line what it is for and which button to press.

Never show raw JSON or script output in the reply. Scripts print one plain line and write their detail to files; read the files.

## What you need before you start

1. **The client config** (`assets/client-config.json`): company, managers, region rule, risk weights, tier thresholds, brand, certifications to feature. Where the member's own copy lives is covered under First run.
2. **The AppFolio export bundle** in one folder (`references/appfolio-exports.md` has every report and its settings). Hard minimum: owner directory, property directory, rent roll. Everything else sharpens the signals; the radar says plainly what is missing.
3. **Owner survey results** through the PropertyManagement.com connector, written to `survey.json` (`references/pmcom-connector.md`). Without them the survey table is empty and the page says so; the likely-detractor table still runs.

## First run: guided setup

The packaged `assets/client-config.json` is the starting point PropertyManagement.com prepared, and inside Claude the package is read-only. The member's own copy lives **in the folder that holds their monthly exports** (`<exports>/client-config.json`), next to `survey.json` and last month's outputs, so it persists from month to month and travels with the data. Always look there first; fall back to the packaged config only to create that copy.

On any run, before the work:

```bash
python3 scripts/setup_config.py init --from assets/client-config.json --to <exports>/client-config.json   # no-op once it exists
python3 scripts/setup_config.py status --config <exports>/client-config.json
```

If `setup_needed` is true (no `setup.completed_at`, or placeholders still open), run the setup conversation before anything else. It is short and it is the reason the outputs come out right:

0. If the PropertyManagement.com connector is connected, call **`pm_org_get`**, save the JSON, and run `python3 scripts/setup_config.py seed --config <exports>/client-config.json --org-json <exports>/org.json` to pre-fill company name, PMID, website, and logo. Then continue with the checklist for everything else. If the connector is missing, skip seeding and ask during the checklist.
1. Print the checklist (`setup_config.py checklist --config ...`) and ask **in one message**, grouped the way the checklist groups them (company, team and direct phones, brand, regions, the newsletter details the config shares with the owner update, fees, risk thresholds), showing the current value for each so the person only has to correct what is wrong. Offer the defaults. Accept partial answers; whatever is not answered stays open and gets asked again next month, it never blocks the run.
   Brand means three things, and the member's output must carry theirs, never the PropertyManagement.com defaults: the **logo** (a hosted image URL for the email header, usually the one on their website; a file for the offline dashboard, embedded with `setup_config.py logo --config <exports>/client-config.json --file <logo>`), the **colours** (primary and accent, hex) and the **fonts** (display and body). When they have no brand kit, read these off their website before asking: the logo from the header image, the primary colour from buttons and the active nav item, the accent from icon highlights, the fonts from the stylesheet's `font-family` or its Google Fonts link. Show what you found and let them correct it.

2. Write the answers with `setup_config.py apply --config <exports>/client-config.json --answers answers.json` (or `--set path=value`) and `--by <name>`. It stamps `setup.completed_at` and reports what is still open.
3. Check the connector once: call `pm_ping`, `pm_truematch_survey_overview`, and **`pm_benchmarks_get`**. Write benchmarks to `<exports>/benchmarks.json` (quote n and as_of in the reply). If the connector is not present, say so in one line and continue without benchmark tiles. Also call `pm_org_get` and confirm the organization name matches `company.name` in the config; a connector signed into a different company must not write this member's `survey.json`. If the connector is absent, quote the member's exact URL from `company.mcp_connector_url` when you say so.
4. Then inventory the exports. On the very first run the person often has none yet: give them the export list with the steps from `references/appfolio-exports.md`, and stop until the folder is filled.

From then on every command takes `--config <exports>/client-config.json`.

## Workflow

### Step 1. Inventory the exports

```bash
python3 scripts/appfolio_loader.py inventory <exports>
```

It names what was recognised (with export dates) and what is missing. If a required report is missing, or any report is older than 45 days, stop and ask for it, quoting the export steps for that exact report from `references/appfolio-exports.md`. Do not run a partial radar silently: the page would score every owner on two signals and call that a list. If the person says "run with what I have", run it and the page carries a gaps banner.

### Step 2. Pull the survey through the connector

Follow `references/pmcom-connector.md`: overview, then list responses, then each response, written to `<exports>/survey.json`. Both shapes (a bare list, or `{"responses": [...]}`) work. Two guards from that reference: if `pm_org_get` names a different company than the config, or the pull returns nothing, keep the `survey.json` already in the folder and say so; never overwrite a good file with an empty one.

### Step 3. Compute

```bash
python3 scripts/appfolio_loader.py features <exports> --out <out> --survey <exports>/survey.json --config <exports>/client-config.json
```

It writes `company.json`, `owners.json`, `inventory.json`, `data-quality.md` and `features-summary.json`. Read `data-quality.md`; anything that changes how the page should be read (blank site managers, Days Vacant reading 0, no Resident work orders, stale lease rows) belongs in your reply, in one line each.

### Step 4. Render

```bash
python3 scripts/render_radar.py --out <out> --config <exports>/client-config.json --benchmarks <exports>/benchmarks.json [--previous <last month>/radar-run.json]
```

It writes `radar-dashboard.html`, `call-list.csv`, `radar-run.json` (keep it; next month's `--previous`) and `radar-summary.json`.

### Step 5. Present it, then say what it means

Show the page first. In claude.ai, read `radar-dashboard.html` and return it as an HTML artifact before you write anything else, so the dashboard is the first thing on screen; in Claude desktop or Claude Code, open the file. Then the reply, from `radar-summary.json`, in this shape:

- **This week's five**, one line each: owner, manager, why (detractor, or likely detractor and the pattern), the play.
- **The survey line**: NPS and the detractor / passive / promoter split, matched respondents, likely detractors.
- **Where they stand**: the one or two benchmark rows that change the conversation (usually renewals).
- **Caveats** from `data-quality.md`, one line each.
- **Two prompts** the manager can ask next ("draft the renewal-win note to X", "prep me on X").

No talk tracks, no scripts, no owner-by-owner essays. The person asked who and why; the page and the play carry the how.

## The scoring model, so you can defend it

Survey detractors are owners who rated the company 0 to 6 on likelihood to recommend; passives 7 to 8; promoters 9 to 10. Likely detractors are owners with **no survey answer** whose operational signals add up to the watch threshold (25 points by default): owner-initiated move-outs, long vacancies, owner payments on hold, no owner payment in 90 days, failed tenancies, turns that sit, management end dates. Weights and thresholds are in the config; the reasoning behind each signal is in `references/risk-model.md`. Say plainly that the likely-detractor table is pattern-based until more survey cycles exist.

Priority on the page: detractor with a vacancy today, then detractor with a renewal inside 90 days, then likely detractor with a vacancy, then with a renewal, then everyone else. A vacancy past the flag threshold is not a lever: the owner keeps their score, but the play falls back to the renewal or to hold, and with nothing else to act on they move to the Flags section. Vacancy age comes from the Unit Vacancy Detail report matched to the rent-roll unit (by name, then the property's only vacancy row), else days since the rent roll's Last Move Out; when neither exists the page says the age is not recorded rather than showing 0. The play per row comes from `references/renewal-play.md`.

## What the dashboard contains, in order

One self-contained HTML file, no libraries, no network, so it opens from a laptop, a shared drive or an attachment.

1. **Survey card**: NPS, the promoter / passive / detractor split, how many respondents matched a live owner.
2. **Against verified property managers**: renewal rate, occupancy, rent collected, NPS and the featured certifications, each next to the PropertyManagement.com median with the gap coloured (from `pm_benchmarks_get` via `--benchmarks`).
3. **This week's five**: cards with the owner, why they are on the list, and the play.
4. **Survey respondents**: a table of detractors (toggle to passives and promoters) with manager, score, what is happening today (vacancy, days, posted or not), the next renewal inside 90 days with the market read, and the play.
5. **Likely detractors**: the same table for non-respondents whose data matches, with the pattern that put them there.
6. **Flags**: owners whose only lever is a vacancy past the threshold (`risk_tiers.long_vacancy_flag_days`, default 100 days). A vacancy that old usually has a reason behind it (renovation, owner hold, a sale in progress), so these owners leave the lists and the week's five and sit here with no action for the week, unless a renewal inside 90 days or a survey detractor score keeps them actionable above.
7. **Since last run** (with `--previous`), **Patterns**, and a collapsed **Data quality** list.

Controls: the manager strip (every manager in the config plus anyone the data names, each with doors and owners managed and the count on the list; a manager with no doors assigned shows as exactly that, which the ops lead wants to know), search, an **Owner view** toggle that hides the tables for an office screen, and **Export list** (CSV, flagged rows included with their own note). Nothing on the page stores notes or statuses; that is the team's task system.

## Rules that do not bend

- Survey answers stay inside the company. The page shows scores, never a quoted comment, and no owner note ever mentions the survey.
- Facts you read can be stated; sequences you inferred are questions, not accusations.
- Never fabricate a number. A missing report means a missing tile and a banner, not an estimate.
- Caps and thresholds come from the config. If someone wants more or fewer rows, change the config, not the output.
- This skill never sends email and never writes to AppFolio or PropertyManagement.com.

## When the data layer is seeded

Once the member's reports are loaded behind the PropertyManagement.com connector, the exports folder becomes optional: the loader reads the same shapes from the connector. Until then, the folder is the source of record.
