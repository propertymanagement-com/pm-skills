# Recommendation rules ("Coming up")

The "Coming up" section is the part of the email an owner acts on, so it is generated from a small rule table rather than free-form writing: the company decides the stance once, in `assets/client-config.json`, and every owner gets the same stance applied to their own facts. At most two sentences per owner, ordered by urgency, duplicates removed.

The horizon starts on the first day of the send month (`--month`), not on the data's as-of date, so a lease that ended last week is never described as coming up.

| Priority | Trigger (per property) | Sentence produced | Needs a human? |
|---|---|---|---|
| 1 | a unit vacant more than 30 days | "Your single-family home has been vacant 62 days." or "2 of 31 units at your 31-unit building at 923 State St have been vacant up to 62 days." (the rent roll shows 33 rows for that building; two are floor-plan placeholders the loader drops) + `[CONFIRM: the pricing or condition change being made to lease them.]` | yes, type the real plan |
| 2 | tenant balance above one month of rent | "A tenant balance of $2,400 is outstanding at your ..." + `[CONFIRM: the collection step under way and the next date.]` | yes |
| 3 | a lease ending within 90 days of the send month | "The lease at your home ends Nov 30." (or "The next lease at your 5-unit building ...") followed by the stance below | no |
| 4 | a unit vacant 30 days or fewer, or a home that has never had a tenant with the company | "Your home is between tenants (12 days so far); Carlos will send the leasing update.", "2 of 6 units at your ... are vacant; ...", or for a new onboarding "Your home is being leased for the first time with us; ..." | no |
| none | nothing above | "No leases end in the next 90 days and nothing is vacant. Nothing you need to decide this month; Carlos will flag anything that changes." | no |

## Renewal stances (priority 3)

Rent vs market comes from the rent roll (rent over market rent, current tenant). `max_increase_pct` in the config caps the proposed increase (default 5).

| Rent vs market | Stance |
|---|---|
| within 5% | "Rent is in line with market, so we recommend renewing at the current rent and keeping a paying tenant in place." |
| more than 5% below | "Rent sits 9% below market, so we will propose an increase toward market, capped at 5%, with the comparison attached." |
| more than 5% above | "Rent is 16% above market; we recommend renewing flat, since a turn would likely reprice the unit down." |
| no market rent, or a gap over 35% (almost always a stale AppFolio market-rent field) | "We will send renewal terms with a current market comparison before then." |

For a multi-unit building the wording switches to "rents" and the building average.

## Naming the property

A single-property owner already read the address in the homes paragraph, so "Coming up" says "your home" / "your 4-unit building". An owner with several properties gets the address each time ("your single-family home at 12 Oak St in Testville") so there is no ambiguity.

## Changing a stance

Edit the sentences in `recommendations()` in `scripts/build_newsletter.py` and mirror the change in the config's `recommendation_rules` (the config is the record the company reads; the code is what runs). Keep the `[CONFIRM: ...]` markers on anything that asserts an action the company has to actually be taking. The builder counts them, the studio flags them, and the send holds them back until a human replaces them.
