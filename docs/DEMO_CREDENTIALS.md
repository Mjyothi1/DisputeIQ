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
