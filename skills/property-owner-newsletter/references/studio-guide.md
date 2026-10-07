# Owner Update Studio, a two-minute guide

For the person who reviews and sends the monthly owner update. Open `newsletter-studio.html` in any browser. Nothing leaves your computer until you export.

## The screen

- **Top bar**: the company and month, the owner picker (name, unit count, manager), the count in this send, and a note if the company update still says `[CONFIRM]`.
- **Filter row** under the top bar: *All*, *Needs a sentence* (rows still carrying `[CONFIRM]`), *Radar: call this week* (owners the Retention Radar says to call before this lands), *Edited*, *No survey*. The readiness bar on the right counts rows ready to send against rows that still need a sentence, and warns while the company update is still the placeholder.
- **Left panel**: the owner's details, then every editable field. Long fields are text boxes. A field turns yellow once you change it.
- **Right panel**: the email exactly as that owner will receive it, rendered from the same template and fields the merge tool will use. It updates as you type.
- **Excluded from this send** (bottom left): who is not getting an email and why (management ended, end date set, no email on file, no active units).

## What to do each month

1. **Fill the company update** once, in the config (`newsletter.company_block`) before the build, so every row carries it. If you missed it, you can still type it per owner here, but that is one edit per owner instead of one for the whole send.
2. **Clear every `[CONFIRM]`.** The builder tells the person running it how many rows carry one; each is a vacancy over 30 days or a balance over a month's rent, and the sentence needs the real plan ("we dropped the asking rent to $1,650 and replaced the carpet"). Ask the property manager, type it in, move on. Rows still carrying `[CONFIRM]` must be removed from the send.
3. **Skim the flagged owners.** The details line shows the Retention Radar tier. `Call this week` owners should hear from their manager before this email lands. Either call first or delete their row from the exported CSV.
4. **Spot-check five.** Pick a single-home owner, the largest owner, a multi-property owner, one with a lease ending, one with a vacancy. Read each as the owner would. Fix anything that reads oddly; the fix applies to that owner only.
5. **Plain text**: the button switches the preview to the text version; some owners' mail clients will show that one.
6. **Export merge CSV.** Downloads `merge-YYYY-MM.csv` with your edits (if the browser blocks downloads, the same text is copied to your clipboard; paste into a blank file). Export JSON keeps a full copy for next month's comparison.
7. **Reset owner** puts one owner back to the generated text if an edit went wrong.

## Sending

Import the exported CSV and `email-template.html` into the mail-merge tool you already use. Map the columns to the `{{tokens}}` (same names). Send one test to yourself, click the report button to check the hosted page opens, then send. Replies come to the sending mailbox, so send from the address the owner's manager actually reads.

## Hosting the report pages

The email's button links to `report_base_url/<token>.html`. Upload the `reports/` folder to that location before sending. Tokens are unguessable and stable, so an owner's link from last month still works after this month's upload replaces the folder. The pages carry the owner's first name and their properties' street addresses, nothing else personal, and no tenant information.
