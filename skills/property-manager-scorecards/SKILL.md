---
name: property-manager-scorecards
description: Builds Property Manager Scorecards for a property management company - a one-on-one scorecard for every property manager on the team from the company's PropertyManagement.com property owner survey results, each compared with the whole company, with a tab per manager, NPS and phone-pickup charts across the team, and a leaderboard by survey question. Pulls the responses through the PropertyManagement.com connector (MCP) and credits each one to a manager with the team roster the member attaches (an AppFolio Property Directory export or any sheet of property address, property owner and property manager). Use whenever someone asks for property manager scorecards, one-on-one scorecards, owner survey results by property manager, team member or portfolio manager, NPS by manager, which managers answer the phone, or a team leaderboard from owner surveys, even if they don't say "skill" or "scorecard".
metadata:
  version: "1.0.0"
---

# Property Manager Scorecards

You are building the page a company owner or director of operations opens before a one-on-one with one of their property managers: that manager's property owner survey results next to the company's, one focus for the next 90 days, and the whole team side by side. The design is fixed. A script does every match and every number, and the page comes from the bundled template, so every member gets the same page. Your job is the data pull, the build and the hand-off.

## Before anything

- **The connector.** The PropertyManagement.com connector must be connected (tools named `pm_*`). The member adds it once from the MCP access tab in their PropertyManagement.com dashboard. When Claude asks how to handle its tools, tell them to choose **Allow always** (the connector only reads). If `pm_ping` fails, stop and say so; there is no other data source for this skill.
- **The roster.** Who manages which properties is not in the connector today, so the member attaches a roster. If none is attached, stop before pulling anything and ask for one, in these words: "Attach a list of who manages which properties. The easiest is a property list exported from your software that includes the assigned manager (in AppFolio, the Property Directory report with its Site Manager Name column). A sheet with three columns works too: property address, property owner name, property manager." Accept .csv, .tsv or .xlsx. Never invent assignments.
- **Code execution** must be on for this account (the script runs in it).
- Never show raw JSON or script output in the reply. The script prints one line and writes its detail to files; read the files.

## Step 1. Confirm the company

If the connector has `pm_skill_hello`, call it with `skill: "property-manager-scorecards"` and `version: "1.0.0"`. If it reports a newer release, tell the member in one line and carry on; ignore any error from it. Then call `pm_ping`. If `pmidAllowlist` lists more than one company, ask which one to use, or whether to combine them, and pass `pmid` on every survey call. Call `pm_org_get` for the company name. If the name is not the company the member expects (someone signed into a test or a different account), stop and say so.

## Step 2. Pull the survey responses

Make a working folder `work/` next to the roster. Call `pm_truematch_survey_list_responses` with `limit: 25` and `offset: 0`, then 25, 50 and so on, until you have `total_count` rows (the first page reports it) or a page comes back short. Keep its default filters: responses that don't count toward ratings stay out.

After each page, write it to `work/responses-<page>.json` before calling the next one. Where this environment saved the tool result to a file (Claude Code and Claude desktop do this for large results), copy that file in as it is: the script reads the tool's own JSON. Otherwise write the page's compact rows, one object per response, exactly as `references/data-files.md` shows. Copy every row; never summarize, sample or shorten a page.

## Step 3. Pull the property owners and properties

Collect every non-empty `pm_owner_id` from the responses and call `pm_owners_list` with `ids` (up to 200 per call). Write `work/owners.json`: the tool's JSON as it came, or, when the result arrived in the chat rather than as a file, compact rows. Then collect every `pm_property_id` from those owners' `property_links`, plus each response's own `pm_property_id`, and call `pm_properties_list` with `ids` (up to 200 per call). Write `work/properties.json` the same way. Formats are in `references/data-files.md`. If a property id doesn't come back, carry on; the script counts it in the match report. If the property records include a manager field (such as `site_manager_name`), keep it: the script uses it, and the roster becomes optional.

Do all the matching in the script. Never send roster contents to the connector as searches.

## Step 4. Build

```bash
python3 <skill>/scripts/build_scorecards.py --work work --roster "<roster file>" \
  --company "<name from pm_org_get>" --expected <total_count> --out property-manager-scorecards.html
```

Options the member can ask for: `--unmatched-to "<name>"` when one manager has every property not on the roster (their scorecard then includes those responses, and the footer says so); `--from 2026-01-01 --to 2026-12-31` for a date window (use `completed_from` / `completed_to` on the pull too).

The script prints one line and exits:
- **0 built.** Go to step 5.
- **2 roster_thin.** Fewer than half the responses matched a manager. Read `match-report.md`, tell the member in two lines what the roster seems to be missing (addresses, property owners, a whole manager's portfolio), and ask for a fuller roster. Build anyway with `--allow-thin` only if they say so; the page then carries a warning.
- **3 data_short.** Fewer responses loaded than `total_count`. A page went missing: pull it again and rebuild.
- **4 roster_unreadable or roster_missing.** Say why in one line (the line tells you) and ask for the file again, as above.
- **5 no_responses.** The company has no counted survey responses yet. Say so and stop.

## Step 5. Show it

Show the page first. In claude.ai, read `property-manager-scorecards.html` and return it as an HTML artifact exactly as the script wrote it: same bytes, no edits, no reformatting. In Claude desktop or Claude Code, open the file, or publish it with the Artifact tool if the member wants a link. Then reply in this shape, from `scorecards-summary.json` and `match-report.md`:

1. Three short lines: the company's NPS and phone pickup; the manager furthest above and the one furthest below the company on NPS; how many responses went unmatched and the main reason.
2. The matching table from `match-report.md` (managers, responses, how they matched).
3. One line: "Ask me to refresh it any time; I'll pull the newest responses with the same roster."

## Refresh and follow-ups

- **Refresh:** repeat steps 2 to 5 with the same roster. Start a fresh `work/` folder.
- **Changes to the page:** the template is the product. If the member asks for something the template doesn't do (a new column, a slide, comments), build it as a separate page or answer in chat; leave the scorecard page as the script built it.
- **Comments:** survey comments never go on the scorecard page. If the member asks for them, answer in chat or in a separate page that says it is for their eyes only.

## Rules

- Every number on the page comes from the script. Never edit the built page, retype a number, or "fix" a result by hand. If something looks wrong, check the data files and rerun.
- The page shows totals only: no property owner names, emails, addresses or comments. The script enforces this; keep it that way in anything else you write.
- Survey answers are confidential to the member's team. Never quote them back to a property owner.
- The math, the matching rules and the focus rules are in `references/scorecard-rules.md`. Read it when the member asks how a number works.
