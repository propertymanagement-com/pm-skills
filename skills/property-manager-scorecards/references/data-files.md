# The data files in `work/`

The script reads every `responses*.json`, `owners*.json` and `properties*.json` in the folder. Each file can be the connector tool's own JSON (the whole result, as the tool returned it) or compact rows. Mixing the two is fine.

## responses-<page>.json

From `pm_truematch_survey_list_responses`. Compact rows, one per response:

```json
[
  {"id": "resp-0001", "owner": "owner-0001", "property": "prop-0001",
   "email": "jane@example.com", "name": "Doe, Jane", "score": 96.5, "date": "2026-09-20",
   "nps": 10, "call": "Picked up",
   "overall": "Very satisfied", "leasing": "Somewhat satisfied", "vacancy": "15-30 days",
   "speed": "Under 24 hours", "cost": "In line with market (fair value)",
   "statements": "Mostly easy to understand"}
]
```

| Compact key | From the response | Notes |
|---|---|---|
| `id` | `id` | used to drop duplicates |
| `owner` | `pm_owner_id` | `null` when empty |
| `property` | `pm_property_id` | `null` when empty |
| `email` | `user_email` | |
| `name` | `user_name` | |
| `score` | `calculated_score` | 0 to 100 |
| `date` | `completed_at` | the date part is enough |
| `nps` | answer titled "Net Promoter Score" | the number, 0 to 10 |
| `call` | answer titled "Call Response" | "Picked up" or "Voicemail" |
| `overall` | "Overall Satisfaction" | the answer's label (`selected_option_label`, else `display_value`) |
| `leasing` | "Leasing Performance" | label |
| `vacancy` | "Vacancy Time" | label |
| `speed` | "Maintenance Communication" | label |
| `cost` | "Maintenance Cost Value" | label |
| `statements` | "Accounting & Financial Reporting" | label |

Copy labels exactly, "Not applicable" included: the script leaves those out of the averages. Leave a key out (or `null`) when the response has no answer for that question. Ignore every other question.

## owners.json

From `pm_owners_list` (called with `ids`):

```json
[{"id": "owner-0001", "name": "Avery and Jordan Collins", "email": "avery@example.com, jordan@example.com",
  "properties": ["prop-0001", "prop-0002"]}]
```

`name` is `display_name`; `email` is the tool's email field as it comes (it can hold several); `properties` lists each `property_links[].pm_property_id`.

## properties.json

From `pm_properties_list` (called with `ids`):

```json
[{"id": "prop-0001", "address": "1842 Tennyson St", "city": "Denver", "zip": "80212", "name": "Tennyson Duplex",
  "source_id": "5012"}]
```

`address` is `address_line1`, `zip` is `postal_code`, `source_id` is the property's id in the member's software. If the record has a manager field (for example `site_manager_name`), add it as `"site_manager_name": "..."`.

## How big these get

A page of 25 responses from the connector is about 90 KB of tool output, and its compact rows about 7 KB. Companies with a few hundred responses take a dozen pages; that runs best in Claude desktop or Claude Code, where large tool results land in files that can be copied straight into `work/`.
