# Abstention threshold calibration

104 answerable, 16 unanswerable questions; score = top cross-encoder logit (`Xenova/ms-marco-MiniLM-L-6-v2`).

Answerable top score: min 0.96, 5th pct 1.93. Unanswerable top score: min -11.20, max 4.60.

| threshold | IDK recall (no LLM call) | false IDK |
|---|---|---|
| -11.0 | 0.06 | 0.00 |
| -10.5 | 0.06 | 0.00 |
| -10.0 | 0.06 | 0.00 |
| -9.5 | 0.06 | 0.00 |
| -9.0 | 0.12 | 0.00 |
| -8.5 | 0.12 | 0.00 |
| -8.0 | 0.12 | 0.00 |
| -7.5 | 0.12 | 0.00 |
| -7.0 | 0.19 | 0.00 |
| -6.5 | 0.25 | 0.00 |
| -6.0 | 0.31 | 0.00 |
| -5.5 | 0.31 | 0.00 |
| -5.0 | 0.31 | 0.00 |
| -4.5 | 0.31 | 0.00 |
| -4.0 | 0.31 | 0.00 |
| -3.5 | 0.38 | 0.00 |
| -3.0 | 0.50 | 0.00 |
| -2.5 | 0.56 | 0.00 |
| -2.0 | 0.56 | 0.00 |
| -1.5 | 0.62 | 0.00 |
| -1.0 | 0.75 | 0.00 |
| -0.5 | 0.81 | 0.00 ← chosen |
| 0.0 | 0.81 | 0.00 |
| 0.5 | 0.81 | 0.00 |
| 1.0 | 0.81 | 0.01 |
| 1.5 | 0.81 | 0.02 |
| 2.0 | 0.88 | 0.06 |
| 2.5 | 0.88 | 0.11 |
| 3.0 | 0.88 | 0.12 |
| 3.5 | 0.94 | 0.21 |
| 4.0 | 0.94 | 0.30 |
| 4.5 | 0.94 | 0.36 |
| 5.0 | 1.00 | 0.42 |
| 5.5 | 1.00 | 0.53 |
| 6.0 | 1.00 | 0.63 |

Chosen: **ABSTAIN_THRESHOLD=-0.5** (false IDK ≤ 2%). Unanswerable questions above it are left to the generator's own "I don't know".
