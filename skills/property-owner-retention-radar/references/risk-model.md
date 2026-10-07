# Risk model

Each owner starts at 0. Signals add or subtract points; the sum picks the tier. Weights and thresholds come from `client-config.json` (`risk_weights`, `risk_tiers`); the defaults below are the shipped values.

| Signal (source) | Default points | Why it is weighted this way |
|---|---|---|
| Management end date already set on a property (Property Directory) | 50 | The owner has decided. The call is an exit interview and a recovery attempt. |
| Move-out recorded as owner-initiated: management terminated, owner selling, owner moved in (Tenant Tickler) | 40 | The departure already happened on one door; the rest of the book is next. |
| Survey detractor, 0-6 on likelihood to recommend (connector) | 40 | Detractors leave and talk. Service recovery within a week changes both. |
| Turn canceled with an owner-exit note: selling, cannot afford, leaving (Work Order status notes) | 30 | Owners exit at the turn; the note is written intent. |
| A unit vacant more than 60 days (Unit Vacancy Detail) | 25 | Long vacancy is the most common trigger for "I'm not sure this is working". |
| Maintenance cost rated significantly above market (survey) | 25 | Platform data: NPS -55 at this answer. |
| A unit vacant 31-60 days | 15 | Early enough to fix with pricing or condition. |
| Survey passive, 7-8 | 15 | Persuadable either way; the open question wins them. |
| Maintenance cost rated somewhat above market (survey) | 15 | Platform data: NPS falls from 73.5 to 8.1 on this one notch. |
| Lease ending within 120 days with no renewal started, per lease (Lease Expiration Detail) | 10, cap 20 | Turnover risk plus a natural reason to call. |
| Tenant balances above one month of the owner's rent (Delinquency) | 10 | Cash-flow stress lands on the owner's statement. |
| First year with the company (Property Directory management start) | 10 | The first months are where trust is won or lost; onboarding gaps surface here. |
| Statements rated confusing (survey) | 10 | The most common improvement ask; cheap to fix. |
| Got voicemail when they called (survey) | 10 | A pickup problem reads as neglect to an owner. |
| Survey promoter, 9-10 | -20 | A healthy relationship absorbs one bad month. |
| Offered a testimonial | -10 | Same. |

Tiers: **Call this week** at 50 points or more, **Watch** from 25 to 49, **Healthy** below 25 with at least one signal, **No signal** when nothing touched the owner (no survey and no operational event). **Departed**: every property carries a past management end date; counted, never called.

Caps: the renderer holds Call this week to `call_cap_total` (10) and `call_cap_per_manager` (5); overflow moves to Watch and is noted. A list longer than a team can work in a week stops being a list.

Judgment the model leaves to you: a written comment. The loader flags "left a written comment" at 0 points so you read it. If the comment changes the picture (a detractor whose complaint was resolved, a promoter who mentions selling), adjust the move and talk track, and say why on the card via the overrides file. Do not edit the score by hand; change the weights in the config if a signal is systematically wrong for this company.

## Additional owner-directory signals

Two owner-directory signals, both from fields the first version ignored:

| Signal | Points (config key) | Fires when | Why it matters |
|---|---|---|---|
| Owner payments on hold | 15 (`payments_on_hold`) | `Hold Payments?` = Yes on an owner at least 6 months in (new onboardings are held until the reserve is funded, so they are skipped) | a hold on a tenured owner is a dispute, a negative balance, or an owner request, and each of those is a retention conversation |
| No owner payment in 90 days | 10 (`no_owner_payment_90d`) | `Last Payment Date` older than 90 days while the owner has leased units and rent posting | the owner's draws have stopped; either the money is going to repairs and balances or the account is broken |

Two rules for how records are counted:

- **One record per inbox.** AppFolio often holds one person as several owner records (a person plus their LLCs, or two records on one property). The loader merges records that share an email: every property once, signals de-duplicated by kind (a vacancy on a shared building counts once), score and tier recomputed. The merged record lists `merged_from`.
- **Co-owners with different inboxes stay separate**, but each record carries `co_owners` (who else is on which property) so the card can say "one call covers the co-owner too".

Delinquency: a tenant in `Evict` status whose move-out date has passed is a former tenant. Their balance is legacy receivable, shown in the health strip's note, and no longer counts toward the owner's "balances exceed a month of rent" signal.

Owner-directory Tags listed in the config's `watch_tags` are counted as a cohort in the Patterns section (for example a fee-waiver cohort with an end date), not scored per owner.

Two more signals, added because early runs kept pointing at failed tenancies and turns that sit:

| Signal | Points (config key) | Fires when | Why it matters |
|---|---|---|---|
| Turn work order open 45+ days | 10 (`turn_open_45d`) | a Unit Turn work order created more than 45 days ago is neither completed nor canceled | the owner experiences the open turn as the vacancy; it is the most visible thing the company controls |
| Former tenant left a balance | 10 (`prior_tenant_loss`) | former tenants (Past, or Evict with a move-out behind us) left more than $3,000, and more than a month of the owner's rent, unpaid across the owner's properties | a failed tenancy hits the owner's wallet and their trust in screening at the same time |

Refinements from early runs:

- **Tenure counts every property the owner ever had with the company**, not just the active ones, so a six-year owner who just added a building is not a "first year" owner; the card carries an informational "long-time owner, new property" line instead.
- **Expiring leases** exclude units already on notice or moving out (those are departures, not renewals to start), rows on vacant units, and rows whose end date disagrees with the rent roll's current Lease To for that unit (the unit was re-leased; the row is the old tenant).
- **Open turns** on a unit that has a tenant who moved in after the work order was opened do not count.
- **Former tenant left a balance** uses a bar of $3,000 or one month of the owner's rent, whichever is higher, so a large building rarely fires it; that is deliberate, the loss has to matter at the owner's scale.
- `watch_tags` matching is a plain substring; make it specific (for example a year-specific waiver tag, not a generic "Fee Waived" that also catches earlier years).
