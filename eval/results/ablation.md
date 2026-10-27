# Retrieval ablation

| collection | config | recall@1 | recall@3 | recall@5 | recall@10 | mrr@10 | search_p50_ms | search_p95_ms | n_questions |
|---|---|---|---|---|---|---|---|---|---|
| librarian | BM25 only | 0.447 | 0.620 | 0.663 | 0.779 | 0.570 | 3.600 | 6.100 | 104 |
| librarian | Dense only | 0.332 | 0.543 | 0.587 | 0.707 | 0.466 | 11.300 | 14.500 | 104 |
| librarian | Hybrid (RRF) | 0.476 | 0.635 | 0.702 | 0.798 | 0.587 | 14.700 | 18.300 | 104 |
| librarian | Hybrid + reranker | 0.447 | 0.697 | 0.755 | 0.798 | 0.591 | 1490.900 | 1883.600 | 104 |
| librarian | Hybrid + reranker + rewrite | 0.438 | 0.692 | 0.750 | 0.798 | 0.583 | 1669.500 | 2386.600 | 104 |
