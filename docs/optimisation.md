# Week 8 optimisation report

Target: **−50% cost per request or p95 latency**, losing **≤ 2 points** of accuracy, measured
before and after on the **same** test set (`data/eval/questions.jsonl`, same commit of the set).

## Baseline (v1.0)

| Metric | Value |
|---|---|
| Correctness | |
| Faithfulness | |
| Recall@5 | |
| p50 / p95 latency (ms) | |
| Avg input / output tokens | |
| Cost / request (list price) | |

Command: `python eval/generation_eval.py --name baseline_v1`

## Changes

One row per change, measured in isolation, then all kept changes together.

| # | Change | Config / commit | Cost/request | p95 ms | Correctness | Faithfulness | Kept? |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |

## Result (v2.0)

| Metric | Before | After | Δ |
|---|---|---|---|

## What did not work
