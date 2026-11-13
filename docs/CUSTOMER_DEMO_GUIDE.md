# Customer portal demo guide

1. Open the landing page and click **Customer login**.
2. Sign in as `meera.iyer@demo.disputeiq.test` (password: see DEMO_CREDENTIALS.md).
3. **Home** shows the masked card (VISA •••• 4021), recent transactions and **My complaints**.
4. Click **Report a problem** (or **Report** next to a transaction).
   - Pick one of the two DemoMart Online ₹2,499 rows.
   - What went wrong: **Charged twice**.
   - Describe it: *I was charged twice for the same order at DemoMart Online. Please refund the extra charge.*
     Hinglish works too: *Ek hi order tha, do baar paise kat gaye.*
5. Submit. You get a reference such as **DIQ-000312** and a **Track this complaint** link.
6. The status moves Submitted → Processing → result, usually within ~10 s with Gemini:
   - **Approved**: the refund was *authorised* automatically (low value, verified duplicate, high confidence). The
     page says plainly that the credit is processed separately and is not confirmed here.
   - **Under review**: a bank specialist will decide (e.g. Gemini confidence below 0.85, or Kavya/Arjun/Sana cases).
7. After a reviewer decides, the same page shows the decision, the bank's letter (when it applies) and the timeline.

What customers never see: reviewer names or notes, evidence checks, AI confidence or model, injection flags.
A customer can only list and open their own transactions and complaints; anything else returns "not found".
