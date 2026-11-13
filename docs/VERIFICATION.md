# Verification status

| Item | Status |
|-|-|
| Local backend tests/lint | Verified in sandbox (see final report for counts) |
| Frontend lint/tsc/tests/build | Verified in sandbox |
| Duplicate guard (SQLite, threads) | Verified; Postgres advisory lock **not** exercised |
| Docker image build | Dockerfile changed (non-root, no dev deps), **not built** here |
| Vercel frontend / Render backend / DB / CORS / live Gemini | **Not independently verifiable**: sandbox egress to those hosts returned HTTP 403 (proxy). Reported by owner / configured in repo (`render.yaml`, `vercel.json`) |
| Render dashboard model/env values | Unknown; set `REVIEWER_ACCOUNTS` there before redeploying or the hosted API will refuse access (503) |
| Live Gemini evaluation | Not run |

**Deployment caution:** the new auth makes the hosted API refuse requests until `REVIEWER_ACCOUNTS` is set on Render and
the new frontend build is deployed; the old frontend will get 401/503. Deploy backend + frontend together.


## Meera transaction visibility (Nov 2026)

* **Reproduced bug (fixed in code):** on the Submit page, changing the customer search kept the previously selected
  customer's id. The page then showed "Customer selected" beside a list containing only Meera, while loading the
  *other* customer's transactions. That matches the production report exactly (catalogue merchants such as NewsNow
  Premium, which a demo customer never has). A regression test covers it; the new picker clears the selection on typing
  and shows the chosen name, masked card and id.
* **Production data: not verified.** The sandbox cannot reach Render. After deploying, select Meera through the new
  picker: the box must read "Demo Customer - Meera Iyer · VISA •••• 4021" and list two DemoMart Online ₹2,499 rows. If it
  does not, the production data itself differs and needs a read-only check.
* Startup seeding now holds a Postgres advisory lock, so overlapping Render instances cannot seed twice (lock path
  not exercised against a real Postgres here).
