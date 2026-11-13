# Demo credentials

No real password or key is stored in this repository. Values below marked *(set on Render)* are whatever you put
in the Render dashboard; share them with judges in person, not in the repo.

## URLs
| Portal | URL |
|-|-|
| Landing page | https://dispute-iq-beryl.vercel.app/ |
| Customer portal | https://dispute-iq-beryl.vercel.app/customer/login |
| Reviewer portal | https://dispute-iq-beryl.vercel.app/reviewer |
| API health | https://disputeiq-backend.onrender.com/health |

## One-click demo sign-in (landing page, reviewer sign-in, customer sign-in)
The **Demo sign-in** box offers *Sign in as priya (reviewer)* and *Sign in as Rohan Desai (customer)*.
- The first time in a browser tab, type priya's reviewer key and the demo customer password into the box. They are
  checked by the normal backend sign-in and remembered **only in that tab** (sessionStorage; gone when the tab
  closes; "Forget demo credentials" clears them). Nothing secret is built into the app.
- After that, each portal header has a **Switch to …** button. Switching signs into the other account through the
  real login, then ends the previous session, so a tab is never signed in as both.
- To hide the box on a non-demo deployment, build the frontend with `VITE_SHOW_DEMO_LOGIN=false`.
- Rohan Desai's login: **rohan.desai@demo.disputeiq.test** (VISA •••• 5533, one DemoBank ATM ₹5,000 transaction).

## Reviewer (bank analyst)
| Name | How to sign in |
|-|-|
| priya | Reviewer access key = the `priya=<key>` value in `REVIEWER_ACCOUNTS` *(set on Render)* |

Reviewers cannot be created through public registration.

## Demo customers
All six share one password: the value of `DEMO_CUSTOMER_PASSWORD` *(set on Render; demo-only, minimum 8 characters)*.
Accounts are created on startup when `BOOTSTRAP_DEMO_CUSTOMERS=true` and `DEMO_CUSTOMER_PASSWORD` is set. Existing
accounts are never changed.

| Email | Customer | Card | Scenario |
|-|-|-|-|
| meera.iyer@demo.disputeiq.test | Demo Customer - Meera Iyer | VISA •••• 4021 | Duplicate ₹2,499 (two identical charges) |
| rohan.desai@demo.disputeiq.test | Demo Customer - Rohan Desai | VISA •••• 5533 | ATM ₹5,000, cash not dispensed |
| kavya.nair@demo.disputeiq.test | Demo Customer - Kavya Nair | VISA •••• 7788 | "Not me" on OTP-authenticated ₹8,750 |
| arjun.mehta@demo.disputeiq.test | Demo Customer - Arjun Mehta | VISA •••• 3190 | Duplicate ₹32,000 (over auto limit) |
| sana.qureshi@demo.disputeiq.test | Demo Customer - Sana Qureshi | VISA •••• 9012 | Duplicate ₹1,800 + prompt injection |
| isha.kapoor@demo.disputeiq.test | Demo Customer - Isha Kapoor | VISA •••• 6644 | Hinglish duplicate ₹999 |

`.test` is a reserved domain: these addresses can never receive email.

Judges can also create their own customer account at `/customer/register`. A new account has no cards or
transactions, so it can sign in but has nothing to dispute.
