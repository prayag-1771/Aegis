"""Aegis command-centre backend.

One API the dashboard talks to. It aggregates the three detection modules
(by HTTP where live, by contract samples where not), keeps a rolling event
store, and exposes the fusion endpoint that produces the correlated
intelligence package.

Port map (team convention):
    8001  fraud-shield-nlp     (Sudarsan)
    8002  counterfeit-vision   (Adharshan)
    8003  fraud-graph-ml       (Prayag)
    8000  command-centre       (this service)
"""

__version__ = "0.1.0"
