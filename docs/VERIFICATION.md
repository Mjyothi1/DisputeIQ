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
