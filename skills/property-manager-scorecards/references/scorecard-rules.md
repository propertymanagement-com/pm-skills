# How the scorecards are worked out

Everything here is implemented in `scripts/build_scorecards.py`. Use this file to explain a number; change the script, not the page.

## The survey

One PropertyManagement.com Property Owner Survey (v1.0) for every company. The scorecards use eight of its questions:

| Survey question | On the page | Answers (value) |
|---|---|---|
| Net Promoter Score | NPS | 0 to 10 |
| Call Response | Phone pickup | Picked up, Voicemail |
| Overall Satisfaction | Overall satisfaction | Very satisfied 10, Somewhat satisfied 7, Neither 5, Somewhat dissatisfied 3, Very dissatisfied 0 |
| Leasing Performance | Tenant placement | same scale as above |
| Vacancy Time | Vacancy time | 0-14 days 10, 15-30 days 8, 31-60 days 5, 61+ days 2, Not applicable (left out) |
| Maintenance Communication | Maintenance response speed | Under 24 hours 10, 1-2 days 8, 3-5 days 5, 6-7 days 3, 7+ days 0, Not applicable (left out) |
| Maintenance Cost Value | Maintenance cost value | Significantly below market 10, Somewhat below 8, In line with market 6, Somewhat above 3, Significantly above 0, Not applicable (left out) |
| Accounting & Financial Reporting | Financial statements | Very easy 8, Mostly easy 6, Somewhat confusing 4, Often confusing 2, Very confusing 0 (scored out of 8, shown out of 10) |

"Not applicable" answers are stored as 0 in the survey, so they would drag averages down. The script leaves them out. Call Response was added to the survey later, so older responses don't have it; they don't count toward phone pickup.

## The numbers

- **NPS:** 9 and 10 are promoters, 7 and 8 passives, 0 to 6 detractors. NPS = % promoters minus % detractors, a whole number with its sign.
- **Phone pickup:** the share of Call Response answers that are "Picked up".
- **Avg satisfaction (0-100):** the average survey score (`calculated_score`), one decimal.
- **The six questions:** the average answer out of 10, one decimal.
- **Company:** every counted response, matched to a manager or not.
- **Gaps and deltas:** manager minus company, worked from the rounded numbers on the page, so the arithmetic on screen always adds up. Rounding is half up (26.5 becomes 27).
- **Strength / Biggest gap:** the question with the largest gap above 0 / below 0. A question needs 3 or more answers from that manager to be picked.
- **Detractors who hit voicemail:** a manager's detractors whose Call Response was Voicemail, out of their detractors who answered it.
- **Sample size:** under 30 responses the card says "small sample, read directionally". Under 5 the manager keeps a tab and a row, numbers show as "-", and they stay off the charts.
- **Colors:** NPS 50 and up green, 0 to 49 amber, below 0 red. Phone pickup 75% and up green, 50 to 74% amber, below 50% red. In the leaderboard, with 3 or more scored managers, each column's best value is green and its worst red.

## Matching a response to a manager

First match wins:
1. **The response's property** (`pm_property_id`): its id in the member's software against a roster property id; else its street address against roster addresses (lowercase, punctuation dropped, St/Street, Ave/Avenue, Rd/Road, Dr/Drive, N/North and the like treated as the same, unit numbers kept with #, Unit and Apt treated as the same, confirmed by ZIP or city); else, when the roster lists the building or every listed unit has one manager, the building; else the property name.
2. **The property owner's properties** (`pm_owner_id`): every property linked to that owner, matched the same way. The manager with the most of them wins. An even split stays unassigned.
3. **Email:** the respondent's email and the property owner's emails against roster emails, when they point to exactly one manager.
4. **Name:** the respondent's name and the property owner's name against roster owner names ("Last, First" equals "First Last"; a couple matches either person; companies and trusts match by full name), when they point to exactly one manager.

A roster row with no manager counts as no match. Unmatched responses go to Unassigned, or to the manager named with `--unmatched-to`. Credit follows today's roster, so a property that changed hands counts for the manager who has it now.

## Focus for the next 90 days

The first rule that fits:
1. **Phone:** half or more of their detractors who answered the phone question got voicemail, or their phone pickup is 10 or more points below the company. "Answer the phone. Their property owners reach a person N% of the time (X points below the company), and ... got voicemail. Nothing else on this card moves faster."
2. **Biggest gap of 0.5 or more below the company:** that question's fix, then "Their property owners rate it A out of 10, against B company-wide."
   - Overall satisfaction: Call every passive and detractor property owner before the next statement goes out.
   - Tenant placement: Walk property owners through the screening behind every new placement.
   - Vacancy time: Shorten vacancies. Price to market on day one and start the turn the day notice comes in.
   - Maintenance response speed: Get back to property owners on every maintenance request within 24 hours, even when the fix takes longer.
   - Maintenance cost value: Show property owners how each repair bill compares to market before they ask.
   - Financial statements: Walk property owners through their monthly statement on a 10-minute call.
3. **A strength:** "Protect the lead on [question]. They're +G above the company there. Ask them to show the team how."
4. **Otherwise:** "Hold the line. Every question sits within half a point of the company. Use this one-on-one to pick the next thing to improve together."
