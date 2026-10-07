# Metric definitions (locked)

Use these exactly. When a number cannot be computed under its definition, show "not available" with the reason. Never substitute a proxy silently.

| Metric | Definition | Notes |
|---|---|---|
| **Occupancy (raw)** | Occupied units / all active units. Occupied = Current, Notice-Rented, Notice-Unrented, Evict. Active = units on properties with no past Management End Date. | Matches the AppFolio total row when Units: Active. |
| **Occupancy (leasable)** | Same numerator; denominator excludes vacant units with no move-out ever recorded (never leased). | The number an operator recognizes. Show both. |
| **Owner-initiated departures** | Tickler move-outs whose reason matches management terminated / owner selling / owner moved in / property sold, plus canceled turns whose status note says the owner is selling, cannot afford, or is leaving. | A floor: blank reasons are common. Say so. |
| **Lease renewal rate** | Renewed / (Renewed + Moved Out) on Lease History for the window. Renewed = fixed-term renewal or month-to-month. Prior-period lease breaks (move-out 45+ days before the window) excluded. | PropertyManagement.com's certification additionally removes departures the tenant did not choose; the radar shows the plain rate and notes the difference. |
| **Rent collected (90 days)** | Paid Amount / Charge Amount on Rent Income (GL 4100) charges with Charge Status: All over the last three full months. | Rent only; fees, late fees and amenities excluded. Short-term stays not excluded in v1. |
| **Turn speed** | Median days from `Created At` to `Work Done On` on completed turns. | Not repair speed unless Resident work orders are present. |
| **Rent vs market** | Sum of rent / sum of computed market rent on occupied units with both values, minus 1. | Units without a market rent on file are excluded and counted. |
| **Days vacant** | AppFolio `Days Vacant`. Zero means no date recorded, not zero days. | Days on Market is a different metric and is not available here. |
| **Owner tenure** | Months since the earliest `Management Start Date` among the owner's active properties. | First-year owners (< 12 months) are a tracked cohort. |
| **NPS** | % of responses 9-10 minus % 0-6 on "How likely are you to recommend". | Report only with n >= 5; label n. |
| **Composite survey score** | PropertyManagement.com's 0-100 weighted score. | Not NPS. A promoter can have a low composite if maintenance-cost value scored low. |
