# Evaluation methodology and results

**Rule: never quote mock numbers as Gemini numbers.** No live-Gemini evaluation has been run (no key/quota in the build
sandbox). The scripts below run it unchanged when a key is present: `--provider gemini`.

| Suite | Command | Data |
|-|-|-|
| Synthetic TEST split | `python -m eval.run_eval --provider mock\|gemini` | 100 template-generated complaints, private in-memory DB (seed 42), labels read only by the harness |
| Hand-authored | `python -m eval.handwritten --provider mock\|gemini` | 33 complaints written by an AI assistant: varied wording, 9 Hinglish, 4 vague, 2 non-existent charges, 6 adversarial, 2 benign look-alikes; one throw-away customer per case |

Both build their own database and never touch the configured one. Labels are never stored in the DB the agent reads
(a test enforces that `app/` never reads `disputes.ground_truth`).

## Results (mock = offline rules, run 2026-11-12)
Synthetic TEST (n=100): reason code 99%, decision 99%, auto-resolution 16% (all correct), unsafe auto 0, injection
detected 3/3. **Circular** (mock classifier shares keywords with the templates).

Hand-authored (n=33): reason code 83.3% (20/24 labelled), amount extraction 88.5% (23/26), merchant 91.3% (21/23),
day 100% (5/5), transaction match 88.9% (24/27, incl. no-match cases), routing 87.9% (29/33), **unsafe auto 0/33**,
abstentions 10/33, failures 0/33, adversarial 6/6 flagged and 0 auto-resolved, benign look-alikes wrongly flagged 0.
The misses are listed in `backend/eval/results/handwritten-mock.md` (e.g. fraud claims classified as goods-not-received,
Hinglish ATM complaint, vague complaints guessed as GNR - all still routed to humans).

Limits: small n (wide error bars), AI-authored text, single seed, mock only. The honest claim is "safety invariants hold
(0 unsafe auto-resolutions) and the offline baseline is imperfect on varied text", not "the system is X% accurate".
