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
   - **Refund authorised**: approved automatically (low value, verified duplicate, high confidence). The page says the
     bank makes the payment separately. DisputeIQ never says a refund was *processed* or *credited*: it has no payment
     integration, so it can't confirm that money arrived.
   - **Under review**: a bank specialist will decide (e.g. Gemini confidence below 0.85, or Kavya/Arjun/Sana cases).
     When the evidence supports the claim the message reads: *"Your dispute is currently under review. Our team has
     identified evidence supporting your claim and is evaluating the appropriate resolution."* The agent's
     recommendation itself is never shown to the customer as an outcome, and no letter is shown until a decision.
7. After a reviewer decides, the same page shows the decision, the bank's letter (when it applies) and the timeline.

What customers never see: reviewer names or notes, evidence checks, AI confidence or model, injection flags.
A customer can only list and open their own transactions and complaints; anything else returns "not found".
