# Property Owner Retention Radar

## Unreleased
- Fix: vacancy age on single-unit properties. The Unit Vacancy Detail lookup by rent-roll unit name missed when the two reports label the unit differently, so real vacancies showed as "0 d" and fell out of the week's five. Ages now match by name, then normalised name, then the property's only vacancy row, then days since Last Move Out; an unknown age reads "age unknown" / "vacancy age not recorded", never 0. Scores, thresholds and who qualifies are unchanged.
- New: Flags section. Vacancies of `risk_tiers.long_vacancy_flag_days` (default 100) or more leave the lists and the week's five and sit at the bottom with no action for the week.
- New: the manager strip lists every configured manager with doors and owners managed and the count on the list; a manager with no doors assigned shows as such.
- New: the dashboard header carries the member's logo on a white plate (`brand.logo_data_uri`, embedded with `setup_config.py logo`) and uses the brand display and body fonts.
- Setup: brand is asked as three things (logo, colours, fonts); with no brand kit, read them off the member's website and confirm. Config carries `company.mcp_connector_url`.
- Docs: the connector URL is per organization and Claude Team admins add custom connectors; `survey.json` is never overwritten by an empty or wrong-company pull; owner directory exports should include inactive owners.
