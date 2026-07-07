"""Aegis Gen AI fusion layer.

Takes the three module outputs (scam detection, counterfeit detection, fraud
graph) and produces ONE correlated intelligence package — the "fusion moment":

    "This scam call is linked to a fraud ring active in this district,
     and a counterfeit note was seized nearby."

Design: a deterministic correlation engine finds the links (auditable — legal
admissibility is a judging metric), then Claude writes the human-readable
narrative. If no API key is configured, a template narrator keeps the demo
alive.
"""

__version__ = "0.1.0"
PROMPT_VERSION = "1.0"
