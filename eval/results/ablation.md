# Retrieval ablation

| collection | config | recall@1 | recall@3 | recall@5 | recall@10 | mrr@10 | search_p50_ms | search_p95_ms | n_questions |
|---|---|---|---|---|---|---|---|---|---|
| librarian | BM25 only | 0.650 | 0.775 | 0.800 | 0.850 | 0.707 | 24.800 | 29.000 | 20 |
| librarian | Dense only | 0.625 | 0.775 | 0.900 | 0.900 | 0.745 | 11.300 | 15.000 | 20 |
| librarian | Hybrid (RRF) | 0.650 | 0.775 | 0.900 | 0.900 | 0.750 | 48.000 | 57.400 | 20 |
| librarian | Hybrid + reranker | 0.650 | 0.775 | 0.875 | 0.900 | 0.739 | 879.300 | 904.100 | 20 |
