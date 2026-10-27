# Chunking experiment (docs subset)

62 answerable questions whose gold sources are docs pages; a hit = chunk from the gold page containing ≥ 60% of the gold passage.

| collection | chunks | mean_tokens | config | recall@1 | recall@5 | recall@10 | mrr@10 | search_p50_ms | n_questions |
|---|---|---|---|---|---|---|---|---|---|
| docs_md_200_60 | 3437 | 134 | Dense only | 0.589 | 0.887 | 0.968 | 0.729 | 10.100 | 62 |
| docs_md_200_60 | 3437 | 134 | Hybrid (RRF) | 0.613 | 0.911 | 0.952 | 0.746 | 12.600 | 62 |
| docs_md_200_60 | 3437 | 134 | Hybrid + reranker | 0.637 | 0.927 | 0.984 | 0.775 | 869.800 | 62 |
| docs_md_400_60 | 2325 | 193 | Dense only | 0.621 | 0.911 | 0.935 | 0.742 | 16.900 | 62 |
| docs_md_400_60 | 2325 | 193 | Hybrid (RRF) | 0.613 | 0.895 | 0.935 | 0.747 | 23.300 | 62 |
| docs_md_400_60 | 2325 | 193 | Hybrid + reranker | 0.613 | 0.927 | 0.935 | 0.759 | 1829.900 | 62 |
| docs_md_800_60 | 1984 | 224 | Dense only | 0.589 | 0.895 | 0.919 | 0.724 | 16.100 | 62 |
| docs_md_800_60 | 1984 | 224 | Hybrid (RRF) | 0.597 | 0.879 | 0.952 | 0.736 | 19.900 | 62 |
| docs_md_800_60 | 1984 | 224 | Hybrid + reranker | 0.661 | 0.944 | 0.952 | 0.792 | 1848.200 | 62 |
| docs_md_400_0 | 2320 | 192 | Dense only | 0.589 | 0.911 | 0.935 | 0.730 | 14.200 | 62 |
| docs_md_400_0 | 2320 | 192 | Hybrid (RRF) | 0.597 | 0.895 | 0.935 | 0.742 | 24.600 | 62 |
| docs_md_400_0 | 2320 | 192 | Hybrid + reranker | 0.629 | 0.927 | 0.935 | 0.768 | 1711.800 | 62 |
| docs_fixed_400_60 | 1392 | 380 | Dense only | 0.637 | 0.879 | 0.952 | 0.755 | 15.400 | 62 |
| docs_fixed_400_60 | 1392 | 380 | Hybrid (RRF) | 0.710 | 0.895 | 0.952 | 0.796 | 19.700 | 62 |
| docs_fixed_400_60 | 1392 | 380 | Hybrid + reranker | 0.750 | 0.911 | 0.984 | 0.830 | 1693.300 | 62 |
