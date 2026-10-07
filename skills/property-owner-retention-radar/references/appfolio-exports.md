# AppFolio exports these skills read

Export every report as **Excel (.xlsx) or CSV, never PDF**, with all columns selected ("select all" in Customize). Set date ranges with the explicit date pickers. Uncheck any box that says "Exclude ... Move Out ...". Upload the files to the Claude Project (or the conversation) in one folder; file names do not matter, the loader recognizes each report by its columns.

| Report (AppFolio > Reporting) | Settings | Used for | Needed for |
|---|---|---|---|
| **Owner Directory** | Customize, select all columns, export | Owner to properties join (`Owner ID`, `Properties Owned IDs`, `Email`, `First Name`) | Both skills |
| **Property Directory** | Properties: All (include inactive), select all columns | Property type, city/zip, `Site Manager Name` (the property manager), `Management Start/End Date`, `Owner ID(s)` | Both skills |
| **Rent Roll** | As of: today. Units: All. Include Non-Revenue Units: No. Select all columns (needs `Property ID`, `Unit ID`, `Status`, `Rent`, `Computed Market Rent`, `Past Due`, `Last Move Out`) | Occupancy, rent vs market, past due, never-leased units | Both skills |
| **Tenant Tickler** | Events: Move-in, Move-out, Notice. Occurred Range: last 6 months to today. Properties: All | Departures, `Move Out Reason` (owner-initiated exits), `Assigned User` | Sharpens |
| **Lease History** | Filter Leases By: Lease End Date. Range: the last three fully closed months. All statuses. Include Non-Revenue Units: Yes. Select all columns (`Outcome`, `Move Out`, `Tenant ID`) | Renewal outcomes by property, region, manager | Sharpens |
| **Renewal Summary** | Lease Range: first window month through one month past window end. Units: All. Statuses: All. Include Tenant Transfers: checked | Renewal pricing (`Percent Difference`), renewal counts | Sharpens |
| **Lease Expiration Detail By Month** | Filter by Lease Expiration Date. Range: this month through ~15 months out. Units: All. Both "Exclude..." boxes UNchecked. Select all columns | Leases ending in the next 120 days, month-to-month tenancies, `Owner(s)` | Newsletter |
| **Unit Vacancy Detail** | Level of Detail: Detail View. Units: All | `Days Vacant`, `Rent Ready`, `Posted To Website` | Newsletter |
| **Work Order** | Status Date: Created On, last 12 months (pickers). Status: All. Work Order Type: All. Properties: Show All | Turn speed (`Created At` to `Work Done On`), canceled turns, `Status Notes`, estimates vs bills | Sharpens |
| **Charge Detail** | Date Type: Charge Date. Range: last three full calendar months. Charge Status: All. GL Accounts: Rent Income (4100) only. Properties: Show All | Rent collected by property and manager (`Charge Amount`, `Paid Amount`) | Newsletter |
| **Delinquency (As Of)** | As of: today. Tenant Status: All (incl. Past). Balance: Greater than 0. Select all columns | Current-tenant balances, evictions; past tenants reported as legacy AR | Newsletter |
| **Unit Directory** | Select all columns | Optional; `Unit Type` is often blank, so property type comes from the Property Directory | Optional |

**Both skills**: a run of either skill stops and asks for these. **Newsletter**: the owner update stops and asks for these; the radar runs without them, with a gaps banner. **Sharpens**: optional for both skills; the outputs say plainly what was missing.

**Facts the loader relies on**
- Property, owner, unit and tenant ids are vendor ids; join on `Property ID` and `Owner ID`, never on names.
- Rows whose property or tenant contains "test" or "zDUMMY" are dropped.
- A property is *active* when `Management End Date` is blank or in the future. Units on inactive properties are excluded from occupancy.
- Vacant units with no `Last Move Out` on record have never been leased (new or offline units); occupancy is reported both raw and on leasable units.
- The work-order export on AppFolio Core often holds unit turns and internal jobs only; resident maintenance may live in Property Meld or similar. The loader says so when it sees no Resident type.
- Charge Detail: `Charge Status: All` keeps unpaid charges in the denominator. `Receipt Type` is display-only.

**Days on Market is not derivable from AppFolio exports.** Use a ShowMojo / Tenant Turner / RentEngine export if leasing speed is needed.
