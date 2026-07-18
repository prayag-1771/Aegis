import sys
sys.path.append('src')
from aegis_fraud_graph.ghost_ring import run_ghost_ring

report = run_ghost_ring(n_banks=4)
print("Recall gap:", report.recall_gap)
print("Matching precision:", report.matching_precision)
print("False-merge rate:", report.false_merge_rate)
