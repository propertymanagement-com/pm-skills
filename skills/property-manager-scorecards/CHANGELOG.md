# Changelog

## 1.0.0 (2026-11-18)

- First release. One page per company: a one-on-one scorecard per property manager against the company, NPS and phone-pickup charts, a leaderboard by survey question. The design follows the Property Manager Scorecards Chuck Hattemer built on 10/11.
- `scripts/build_scorecards.py` does every match and number; `assets/scorecards-template.html` is the page.
- Rosters: AppFolio Property Directory exports (Site Manager Name) or any sheet with property address, property owner and property manager; .csv, .tsv or .xlsx.
- Uses a manager field on the connector's property records when one appears, so the roster becomes optional for those companies.
