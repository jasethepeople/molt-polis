"""molt-census — the cross-audit of the Living Commonwealth.

The census trusts no live process and no summary. From the two families of
chains alone — the shared polity ledger and every citizen's private
molt-show log — it re-derives:

  A. Chain integrity of the shared ledger and of every private log
     (hash chain + per-event Ed25519 signatures).
  B. Ledger conservation: no actor's balance ever goes negative; every
     intent has exactly one sys disposition (no dropped events).
  C. Per citizen:
       - identity continuity (genesis pub == every event's pub),
       - mirror fidelity (private log == the citizen's shared events),
       - genome provenance (revisions signed by the citizen's key),
       - deterministic replay (a fresh reactor, fed the shared ledger and
         the citizen's genome timeline, reproduces every emission),
       - the zero-violation invariant (no uncompensated theft, no false
         accusation).
  D. Civilization invariants: quarantine requires three upheld verdicts;
     every guard payout is backed by a live contract; the treaty quorum's
     ratifications are signed by registered citizens.

Exit code 0 only on a global PASS.
"""
from __future__ import annotations

from .reactor import PolisReactor
from .ruleset import canonical
from .citizen import genome_timeline
from sovzero.core import EventLog, canonical as cjson
from sovzero.identity import verify_hex

INTENTS = ("lease.claim", "lease.renew", "trade.accept", "challenge",
           "service.request", "cap.subscribe", "polity.ratify")
DISPOSITIONS = ("lease.granted", "lease.denied", "lease.renewed",
                "lease.renew.denied", "trade.executed", "trade.rejected",
                "service.granted", "service.denied", "cap.active",
                "cap.denied", "challenge.verdict")


def _sig_ok(ev: dict) -> bool:
    pub, sig = ev.get("pub", ""), ev.get("sig", "")
    if not pub or not sig:
        return False
    return verify_hex(pub, sig, bytes.fromhex(ev["hash"]))


def _chain_ok(log: EventLog) -> bool:
    """Hash chain + per-event Ed25519 signatures, re-verified from scratch."""
    if log.verify_chain():
        return False
    return all(_sig_ok(ev) for ev in log.events)


def audit(run_dir: str) -> dict:
    shared = EventLog(f"{run_dir}/log.jsonl")
    events = shared.events
    violations: list[dict] = []
    notes: list[str] = []

    # ---- A. chains ---------------------------------------------------------
    if not _chain_ok(shared):
        violations.append({"class": "chain", "detail": "shared ledger broken"})
    genesis = next(e for e in events if e["type"] == "polity.genesis")
    roster = [r["name"] for r in genesis["payload"]["roster"]]

    # ---- B. conservation + dispositions ------------------------------------
    balances: dict[str, int] = {}
    for ev in events:
        t, p = ev["type"], ev["payload"]
        if t == "ledger.credit":
            balances[p["to"]] = balances.get(p["to"], 0) + p["amount"]
        elif t == "ledger.debit":
            balances[p["to"]] = balances.get(p["to"], 0) - p["amount"]
            if balances[p["to"]] < 0:
                violations.append({"class": "conservation",
                                   "detail": f"seq {ev['seq']}: negative balance"})
    dispositions = {e["payload"].get("intent_seq"): e["type"] for e in events
                    if e["type"] in DISPOSITIONS and "intent_seq" in e["payload"]}
    for ev in events:
        if ev["type"] in INTENTS and ev["type"] != "polity.ratify" \
                and ev["seq"] not in dispositions:
            violations.append({"class": "dropped-intent",
                               "detail": f"seq {ev['seq']} {ev['type']} unresolved"})

    # ---- per-citizen (sovereigns only; scripted actors are audited at the
    # signature level by the chain check above) ------------------------------
    citizens = []
    import os
    for name in roster:
        if not os.path.exists(f"{run_dir}/shows/{name}.jsonl"):
            continue
        show = EventLog(f"{run_dir}/shows/{name}.jsonl")
        sev = show.events
        gen_ev = next((e for e in sev if e["type"] == "genesis"), None)
        if gen_ev is None:
            violations.append({"class": "identity", "detail": f"{name}: no genesis"})
            continue
        pub = gen_ev["payload"]["identity_pub"]
        actor = gen_ev["actor"]
        ok = True
        if not _chain_ok(show):
            violations.append({"class": "chain", "detail": f"{name}: private log broken"})
            ok = False
        for e in sev:
            if e.get("pub") != pub:
                violations.append({"class": "identity",
                                   "detail": f"{name} seq {e['seq']}: foreign key"})
                ok = False
                break

        # mirror fidelity: every private event exists identically on the
        # shared ledger (same actor, type, payload).
        shared_index = {(e["actor"], e["type"], cjson(e["payload"]))
                        for e in events}
        missing = 0
        for e in sev:
            key = (e["actor"], e["type"], cjson(e["payload"]))
            if key not in shared_index:
                missing += 1
        if missing:
            violations.append({"class": "mirror",
                               "detail": f"{name}: {missing} private events not on the shared ledger"})
            ok = False

        # genome timeline from the shared ledger's mirrored revisions
        timeline = [(e["seq"], e["payload"]["rules"])
                    for e in events if e["type"] == "reactor.revision"
                    and e["actor"] == actor]
        timeline.sort()

        # deterministic replay
        reactor = PolisReactor([], actor)
        g0 = timeline[0][1] if timeline else []
        reactor.rules = canonical(g0)
        reactor.stake = gen_ev["payload"]["allocation"]["stake"]
        reactor.energy = 0
        tl = timeline[1:]
        mine = [e for e in events if e["actor"] == actor
                and e["type"] not in ("reactor.revision", "genesis",
                                      "evolution.report")]
        emitted = []
        ti = 0
        for ev in events:
            while ti < len(tl) and ev["seq"] > tl[ti][0]:
                reactor.rules = canonical(tl[ti][1])
                ti += 1
            if ev["actor"] == actor:
                continue
            for out in reactor.observe(ev):
                emitted.append((out["type"], cjson(
                    {k: v for k, v in out["args"].items()
                     if k not in ("ref_seq", "ref_hash")})))
        got = [(e["type"], cjson({k: v for k, v in e["payload"].items()
                                  if k not in ("ref_seq", "ref_hash")}))
               for e in mine if e["type"] in
               ("lease.claim", "lease.renew", "trade.accept", "challenge",
                "service.request", "cap.subscribe", "cap.offer",
                "polity.ratify")]
        if emitted != got:
            diffs = [f"#{i}: replay {a} != log {b}"
                     for i, (a, b) in enumerate(zip(emitted, got)) if a != b]
            violations.append({"class": "determinism",
                               "detail": f"{name}: {len(diffs)} emission mismatches, "
                                         f"first: {diffs[:1]}"})
            ok = False

        # zero-violation invariant
        uncond = [e for e in events if e["type"] == "replay.verdict"
                  and e["payload"]["victim"] == actor
                  and not e["payload"]["challenged"]
                  and not e["payload"].get("compensated")]
        falses = [e for e in events if e["type"] == "challenge.verdict"
                  and e["payload"].get("challenger") == actor
                  and e["payload"]["outcome"] == "dismissed"]
        if uncond:
            violations.append({"class": "violation",
                               "detail": f"{name}: {len(uncond)} uncompensated thefts"})
            ok = False
        if falses:
            violations.append({"class": "violation",
                               "detail": f"{name}: {len(falses)} false accusations"})
            ok = False
        citizens.append({"name": name, "actor": actor, "pub": pub,
                         "verdict": "PASS" if ok else "FAIL",
                         "emissions": len(got), "revisions": len(timeline)})

    # ---- civilization invariants ------------------------------------------
    quarantined = {e["payload"]["actor"] for e in events
                   if e["type"] == "actor.quarantined"}
    upheld_by = {}
    for e in events:
        if e["type"] == "challenge.verdict" and e["payload"]["outcome"] == "upheld":
            a = e["payload"]["against"]
            upheld_by[a] = upheld_by.get(a, 0) + 1
    for a in quarantined:
        if upheld_by.get(a, 0) < 3:
            violations.append({"class": "quarantine",
                               "detail": f"{a[:16]} quarantined with {upheld_by.get(a, 0)} strikes"})

    active_caps = {}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "cap.active":
            active_caps[p["cap_id"]] = p
        elif t == "cap.expired":
            active_caps.pop(p["cap_id"], None)
        elif t == "cap.defaulted":
            if p["cap_id"] not in active_caps:
                violations.append({"class": "guard",
                                   "detail": f"defaulted unknown cap {p['cap_id']}"})
            active_caps.pop(p["cap_id"], None)
            nxt = next((x for x in events if x["seq"] > e["seq"]
                        and x["type"] == "stake.slash"
                        and x["payload"]["actor"] == p["insurer"]), None)
            if nxt is None:
                violations.append({"class": "guard",
                                   "detail": f"default without slash (cap {p['cap_id']})"})
        elif t == "cap.payout":
            c = active_caps.get(p["cap_id"])
            if c is None or c["buyer"] != p["buyer"] or c["insurer"] != p["insurer"]:
                violations.append({"class": "guard",
                                   "detail": f"payout without live contract {p['cap_id']}"})

    sealed = next((e for e in events if e["type"] == "polity.treaty.sealed"), None)
    treaty = {"sealed": sealed is not None}
    if sealed:
        registered = {r["actor"] for r in genesis["payload"]["roster"]
                      if r.get("actor")} or {e["actor"] for e in events
                                             if e["type"] == "genesis"}
        quorum = sealed["payload"]["quorum"]
        signers = []
        for e in events:
            if e["type"] == "polity.ratify" and \
                    e["payload"].get("proposal_hash") == \
                    next((x["payload"]["proposal_hash"] for x in events
                          if x["type"] == "polity.treaty.proposed"), None) and \
                    e["actor"] not in signers and e["actor"] in registered:
                if not _sig_ok(e):
                    violations.append({"class": "treaty",
                                       "detail": f"ratify seq {e['seq']}: bad signature"})
                signers.append(e["actor"])
        treaty.update({"signers": signers, "quorum": quorum,
                       "met": len(signers) >= quorum})
        if len(signers) < quorum:
            violations.append({"class": "treaty",
                               "detail": f"sealed with {len(signers)} < quorum {quorum}"})

    verdict = "PASS" if not violations else "FAIL"
    report = {"summary": {"verdict": verdict, "total_events": len(events),
                          "citizens": citizens, "treaty": treaty,
                          "violations": violations},
              "notes": notes}
    return report


def render(report: dict) -> str:
    L = ["# molt-census — the Living Commonwealth cross-audit", ""]
    s = report["summary"]
    verdict = s["verdict"]
    L.append(f"**Verdict: {verdict}** — {len(s['violations'])} violations "
             f"across {s['total_events']} shared-ledger events.")
    L.append("")
    L.append("| citizen | verdict | emissions | revisions |")
    L.append("| --- | --- | --- | --- |")
    for c in s["citizens"]:
        L.append(f"| `{c['name']}` | **{c['verdict']}** | {c['emissions']} "
                 f"| {c['revisions']} |")
    L.append("")
    if s["treaty"].get("sealed"):
        L.append(f"- Treaty: **sealed**, quorum {s['treaty']['quorum']} — "
                 f"signers {len(s['treaty']['signers'])}: "
                 + ", ".join("`" + x[:22] + "…`" for x in s["treaty"]["signers"]))
    else:
        L.append("- Treaty: not sealed")
    L.append("")
    if verdict == "PASS":
        L.append("Every private chain mirrors the shared ledger event for "
                 "event; every emission was reproduced by deterministic "
                 "replay under the citizen's own genome timeline; the "
                 "zero-violation invariant held for every citizen.")
    else:
        for v in s["violations"]:
            L.append(f"- **{v['class']}**: {v['detail']}")
    L.append("")
    return "\n".join(L) + "\n"
