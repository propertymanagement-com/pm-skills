# Data model the skills share

```
Owner (Owner Directory: Owner ID, Name, First Name, Email, Properties Owned IDs)
  └── Property (Property Directory: Property ID, Property Type, City, Zip, Site Manager Name, Management Start/End Date, Owner ID(s))
        ├── Units (Rent Roll: Unit ID, Status, Rent, Computed Market Rent, Past Due, Lease To, Last Move Out)
        ├── Vacancies (Unit Vacancy Detail: Days Vacant, Rent Ready, Posted To Website)
        ├── Leases ending (Lease Expiration Detail: Lease Expires, Renewal Start Date, Notice Given Date, Rent, Computed Market Rent)
        ├── Renewal outcomes (Lease History: Outcome, Lease End, Move Out; Renewal Summary: Percent Difference)
        ├── Departures (Tenant Tickler: Event=Move-out, Move Out Reason, Assigned User)
        ├── Turns / work (Work Order: Created At, Work Done On, Status, Status Notes, Vendor, Estimate Amount, Vendor Bill Amount)
        ├── Rent charges (Charge Detail: Account Number 4100, Charge Amount, Paid Amount)
        └── Balances (Delinquency: Tenant Status, Amount Receivable, Delinquent Rent)
Survey response (connector) joins to Owner by email.
```

Loader outputs
- `inventory.json`: reports found, rows, exported-on dates, missing list.
- `company.json`: portfolio, departures, renewals, vacancy, turns, collections, delinquency, team, survey aggregates; each block null when its report is missing.
- `owners.json`: ranked owners with `score`, `tier`, `signals[]` (points, text, type), portfolio numbers, `survey` (latest response), `properties_detail[]`.
  - each `properties_detail[]` entry: `property_id`, `type`, `city`, `zip`, `address` (street line from the property directory, so an owner-facing sentence can say "your home at 100 Example St"), `manager`, `managed_since`, `units`, `occupied`, `rent_month`, `rent_vs_market_pct` (occupied units only; a gap over 35% is almost always a stale market-rent field), `past_due`, `next_lease_end` + `expiring_120d`, `m2m_units`, `vacant_units` + `max_days_vacant` + `rent_ready`, `turns_12mo` + `turn_median_days`, `collected_90d_pct` + `charged_90d` (rent GL only).
- `data-quality.md`: notes that change how numbers should be read.

Tiers: `Call this week` (score >= 50), `Watch` (25-49), `Healthy` (< 25 with signals), `No signal` (no data touched the owner). Caps and weights live in the client config (`risk_tiers`, `risk_weights`).
