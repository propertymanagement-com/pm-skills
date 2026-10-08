# The PropertyManagement.com connector (MCP)

The member connects Claude to their organization's own URL, **`https://mcp.propertymanagement.com/api/mcp/v1/orgs/<org-id>`**, through Settings > Connectors > Add custom connector, then signs in with their PropertyManagement.com login (OAuth through app.propertymanagement.com; no key to paste). Copy the org-specific URL from the PM.com Client Dashboard MCP page; the setup also stores it in the client config as `company.mcp_connector_url`, so quote that value verbatim whenever you tell someone how to add the connector. There is no generic URL: the bare `/mcp` path returns 404. On a Claude Team or Enterprise plan a workspace admin adds the custom connector; everyone else hard-refreshes Claude, finds it under Settings > Connectors, and connects with their own PM.com login, or the admin connects it once for the whole organization. Access is enabled per organization by PropertyManagement.com. Tool names appear as `pm_*`.

## Start of every run

1. **`pm_skill_hello`** with `{ "skill": "property-owner-newsletter", "version": "0.1.0" }` (read `version` from this skill's frontmatter). If the response has `is_latest: false`, mention once that a newer release is available and where to install it; do not nag again in the same conversation.
2. **`pm_ping`** — confirms the connection and lists the directory company ids (`pmidAllowlist`). If this fails, the connector is not connected or not enabled: tell the user, then continue with uploaded files only and mark survey-derived tiles "not available".
3. **`pm_org_get`** — organization name, PMID, website, logo. On first setup, pass the JSON to `setup_config.py seed --org-json …` before the guided checklist (see First run in `SKILL.md`).
4. **`pm_benchmarks_get`** — dated verified-PM medians and owner-survey aggregates (`version`, `as_of`, `source`, `notes`, `certified_metrics[]`, `owner_survey[]`). Save the response to `<exports>/benchmarks.json` and pass `--benchmarks` to `build_newsletter.py`. Quote every number with **n** and the **as_of** date. If the connector is unavailable, say benchmarks are unavailable — do not invent medians.

## Two guards before writing survey.json
- **Right company?** `pm_org_get` returns the organization name and its pmids. If the name does not match `company.name` in the config (a person signed into the wrong PM.com account, or a test organization), say so and do not write `survey.json` from this connector; keep whatever `survey.json` is already in the folder.
- **Never overwrite a good file with an empty pull.** If the overview reports zero responses, a tool errors, or the pull comes back shorter than the file already in the folder, keep the existing `survey.json`, say which date it carries, and move on. A connector hiccup must not erase last month's survey picture.

## Property owner surveys (works today)

- `pm_truematch_survey_overview` (pmid): survey title, response counts, average and median composite score, distribution, recent samples.
- `pm_truematch_survey_list_responses` (pmid, limit up to 200, offset, completed_from/to, min_score/max_score, has_testimonial): completed responses with `user_name`, `user_email`, `calculated_score`, `comment`, testimonial text/status and `answers` (question title, display value, numeric value). Page until the count matches the overview.
- `pm_truematch_survey_get_response` (response_id): one response in full.

Turn the responses into the survey file the loader reads (`survey.json`), one object per response:
```json
{"email": "owner@example.com", "name": "Jane Doe", "completed_at": "2026-08-12",
 "nps": 9, "score": 94.0, "overall": "Very satisfied", "leasing": "Very satisfied",
 "vacancy": "15-30 days", "maintenance_comms": "Under 24 hours",
 "maintenance_cost": "In line with market (fair value)", "accounting": "Mostly easy to understand",
 "call_response": "Picked up", "comment": "...", "has_testimonial": true, "testimonial_approved": false}
```
Map answers by question title: Net Promoter Score -> nps (numeric), Overall Satisfaction -> overall, Leasing Performance -> leasing, Vacancy Time -> vacancy, Maintenance Communication -> maintenance_comms, Maintenance Cost Value -> maintenance_cost, Accounting & Financial Reporting -> accounting, Call Response -> call_response.

Survey answers are confidential to the property manager's team. They inform calls and service recovery; they are never published or quoted back to the owner.

## Portfolio tools (properties, units, leases, owners, work orders, charges, payments, listings, renewals)

Return data once the member's AppFolio feed is synced or their monthly exports are loaded into the data layer. Until then they return empty results for this company; use the uploaded exports. When they do return rows, prefer them for the same fields the loader computes, and say which source produced each tile.

## Limits to remember

- Page size max 200; no aggregate tools, so summarize from pages.
- Survey responses link to an owner only by exact email (or name); properties attach only when the owner has exactly one. The owner directory upload is the reliable join.

`survey.json` may be either a bare list of responses or an object `{"source": ..., "responses": [...]}`; the loader accepts both.
