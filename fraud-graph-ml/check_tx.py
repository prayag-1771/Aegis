import sys
sys.path.append('src')
from aegis_fraud_graph.data import load
ds = load("synthetic")
tx = ds.transactions
print("Total cross edges?:", len(tx))
dups = tx.duplicated(subset=['amount', 'timestamp'])
print("Duplicates in amount+timestamp:", dups.sum())
