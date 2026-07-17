"""Response-action engine — the platform's 'disrupt / respond' step.

Detection tells you *what* is happening; this turns it into *what to do about it*:
a concrete, timestamped, auditable action aimed at a specific recipient — freeze a
mule account, block a scam number, alert I4C/MHA, hold a victim's transfer, or push
an intelligence package to an investigating officer.

Everything here is DETERMINISTIC and rule-based (no LLM in the decision path), so
each action is fully explainable and court-auditable. Dispatch is *simulated* for
the demo — no live bank/telecom/government integration is connected — and every
action says so. The engine never asserts guilt; it produces decision-support
recommendations with an evidence chain (`trigger.refs`) and an append-only audit log.

Actions are derived from the same signals the dashboard already holds:
  * fusion `money_trails`      -> account_freeze (victim money traced into a mule acct)
  * high-risk fraud-graph rings-> account_freeze (mule accounts inside a detected ring)
  * active scam detections     -> telecom_block + citizen_intercept (pre-transfer)
  * fusion threat_level high   -> mha_alert (consolidated national alert)
  * coordinated campaigns/hubs -> review_queue (intelligence package to an officer)
"""

from __future__ import annotations

from datetime import datetime, timezone

DISCLAIMER = (
    "Decision-support recommendation with a full evidence chain. Dispatch is "
    "SIMULATED for demonstration — no live bank/telecom/MHA integration is "
    "connected. This action does not assert guilt; verify against source records "
    "before any real-world enforcement."
)

# Target time-to-action per priority, in minutes — used to show lead time against
# the fraud clock (a UPI transfer clears in seconds; a freeze must beat cash-out).
SLA_MINUTES = {"critical": 30, "high": 120, "medium": 1440}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitize(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-+" else "_" for ch in str(text))


def _action(
    *,
    action_type: str,
    primary_target: str,
    title: str,
    priority: str,
    recipient: str,
    trigger: dict,
    target: dict,
    payload: dict | None = None,
) -> dict:
    """Assemble one action record with a stable id and an opening audit entry."""
    now = _now()
    return {
        "action_id": f"{action_type}:{_sanitize(primary_target)}",
        "created_at": now,
        "action_type": action_type,
        "title": title,
        "priority": priority,
        "status": "proposed",
        "recipient": recipient,
        "trigger": trigger,
        "target": target,
        "payload": payload,
        "sla_minutes": SLA_MINUTES.get(priority),
        "audit": [
            {"at": now, "actor": "aegis-engine", "event": "proposed", "note": trigger["rationale"]}
        ],
        "simulated": True,
        "disclaimer": DISCLAIMER,
    }


def derive_actions(
    scams: list[dict],
    counterfeits: list[dict],
    fraud_graph: dict | None,
    fusion: dict | None,
) -> list[dict]:
    """Deterministic rules → a de-duplicated, priority-sorted action list.

    De-dup is by `action_id` (action_type + primary target): the same mule account
    seen via a money-trail and via its ring yields one freeze, not two.
    """
    by_id: dict[str, dict] = {}

    def _put(action: dict) -> None:
        # First rule to name a target wins its slot; later rules only add if new.
        by_id.setdefault(action["action_id"], action)

    graph = fraud_graph or {}
    rings = {r["ring_id"]: r for r in graph.get("rings", [])}

    # 1) account_freeze — victim money traced into a mule account (strongest signal:
    #    fusion has already linked a specific payment to a specific ring account).
    for mt in (fusion or {}).get("money_trails", []):
        acct = mt.get("account_id")
        if not acct:
            continue
        amount = mt.get("amount")
        ring_id = mt.get("ring_id")
        _put(
            _action(
                action_type="account_freeze",
                primary_target=acct,
                title=f"Freeze mule account {acct}"
                + (f" — ₹{int(amount):,} traced in" if amount else ""),
                priority="critical",
                recipient="Beneficiary bank via NPCI",
                trigger={
                    "source": "fusion.money_trail",
                    "refs": [r for r in (mt.get("scam_event_id"), ring_id) if r] + [acct],
                    "rationale": (
                        "Victim payment traced into this account inside a detected "
                        "fraud ring — freeze before layering/cash-out."
                    ),
                },
                target={
                    "account_id": acct,
                    "ring_id": ring_id,
                    "amount": amount,
                    "district": mt.get("district"),
                    "scam_event_id": mt.get("scam_event_id"),
                },
                payload={
                    "request": "account_freeze",
                    "account_id": acct,
                    "ring_id": ring_id,
                    "amount_inr": amount,
                    "basis": "victim-payment traceback (fusion money-trail)",
                },
            )
        )

    # 2) account_freeze — mule accounts inside a high-risk ring even without a
    #    payment traceback yet. Cap to the top accounts of the riskiest rings so the
    #    queue stays actionable, not a dump of every node.
    hot_rings = sorted(
        (r for r in rings.values() if float(r.get("risk_score", 0)) >= 0.7),
        key=lambda r: float(r.get("risk_score", 0)),
        reverse=True,
    )[:3]
    for ring in hot_rings:
        for acct in (ring.get("account_ids") or [])[:3]:
            _put(
                _action(
                    action_type="account_freeze",
                    primary_target=acct,
                    title=f"Freeze account {acct} — in ring {ring['ring_id']}",
                    priority="high",
                    recipient="Beneficiary bank via NPCI",
                    trigger={
                        "source": "fraud_graph.ring",
                        "refs": [ring["ring_id"], acct],
                        "rationale": (
                            f"Account is a node in ring {ring['ring_id']} "
                            f"(risk {round(float(ring.get('risk_score', 0)) * 100)}%) — "
                            "review for freeze."
                        ),
                    },
                    target={
                        "account_id": acct,
                        "ring_id": ring["ring_id"],
                        "amount": ring.get("total_amount"),
                        "district": ring.get("district"),
                    },
                    payload={
                        "request": "account_review_freeze",
                        "account_id": acct,
                        "ring_id": ring["ring_id"],
                        "ring_risk": ring.get("risk_score"),
                    },
                )
            )

    # 3) telecom_block + citizen_intercept — an active, non-legit scam with a number.
    for s in scams:
        if s.get("verdict") == "legit":
            continue
        risk = float(s.get("risk_score", 0))
        if risk < 0.6:
            continue
        eid = s.get("event_id", "unknown")
        phone = s.get("phone_number")
        district = (s.get("location_hint") or {}).get("district")
        scam_type = (s.get("scam_type") or "scam").replace("_", " ")

        if phone:
            _put(
                _action(
                    action_type="telecom_block",
                    primary_target=phone,
                    title=f"Block number {phone} — active {scam_type}",
                    priority="high",
                    recipient="DoT / operator (CEIR)",
                    trigger={
                        "source": "scam.detection",
                        "refs": [eid, phone],
                        "rationale": (
                            f"Number used in an active {scam_type} "
                            f"(risk {round(risk * 100)}%) — block to stop further calls."
                        ),
                    },
                    target={"phone_number": phone, "scam_event_id": eid, "district": district},
                    payload={
                        "request": "number_block",
                        "msisdn": phone,
                        "reason": scam_type,
                        "markers": s.get("markers", []),
                    },
                )
            )

        # Pre-transfer intercept: the money has not (yet) been reported as paid, so a
        # warning / transaction hold can still stop victimisation. This is the most
        # genuinely *predictive* action — it fires at the point of contact.
        if not (s.get("reported_payment") or {}).get("amount"):
            _put(
                _action(
                    action_type="citizen_intercept",
                    primary_target=eid,
                    title=f"Warn potential victim — active {scam_type}",
                    priority="critical",
                    recipient="Potential victim + payer bank (transaction hold)",
                    trigger={
                        "source": "scam.detection",
                        "refs": [eid] + ([phone] if phone else []),
                        "rationale": (
                            "High-risk scam flagged at point of contact with no payment "
                            "yet recorded — intercept before transfer."
                        ),
                    },
                    target={"scam_event_id": eid, "phone_number": phone, "district": district},
                    payload={
                        "request": "citizen_warning",
                        "scam_type": s.get("scam_type"),
                        "advice": (
                            "No government agency arrests over a video call or asks you to "
                            "move money to a 'safe account'. Do not pay. Report to 1930."
                        ),
                    },
                )
            )

    # 4) mha_alert — consolidated national alert when fusion says the picture is hot.
    threat = (fusion or {}).get("threat_level", "low")
    if threat in ("high", "critical"):
        _put(
            _action(
                action_type="mha_alert",
                primary_target="national",
                title=f"MHA/I4C alert — threat level {threat}",
                priority="high" if threat == "high" else "critical",
                recipient="I4C / MHA (NCRP 1930)",
                trigger={
                    "source": "fusion",
                    "refs": [ls.get("ref_event_id") for ls in (fusion or {}).get("linked_signals", []) if ls.get("ref_event_id")]
                    or ["fusion"],
                    "rationale": (
                        f"Fusion correlated multiple domains into a {threat} threat picture — "
                        "escalate to the national cybercrime coordination centre."
                    ),
                },
                target={"district": None},
                payload={
                    "request": "national_alert",
                    "threat_level": threat,
                    "summary": (fusion or {}).get("summary", ""),
                    "correlation_basis": (fusion or {}).get("correlation_basis", []),
                    "recommended_actions": (fusion or {}).get("recommended_actions", []),
                },
            )
        )

    ranked = sorted(
        by_id.values(),
        key=lambda a: (
            {"critical": 0, "high": 1, "medium": 2}.get(a["priority"], 3),
            a["created_at"],
        ),
    )
    return ranked
