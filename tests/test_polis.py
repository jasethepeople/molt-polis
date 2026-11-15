"""test_polis.py — invariant checks for the Living Commonwealth.

Run from the project root: python3 tests/test_polis.py
Exit code non-zero on any failure. Requires runs/default (created by
`python3 -m moltpolis run`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from moltpolis.census import audit                      # noqa: E402
from moltpolis.citizen import genome_timeline           # noqa: E402
from moltpolis.reactor import PolisReactor              # noqa: E402
from moltpolis.ruleset import canonical, initial_rules  # noqa: E402
from sovzero.core import EventLog                       # noqa: E402

RUN = Path("runs/default")
failures: list[str] = []
passed = 0


def check(name: str, cond: bool, detail: str = ""):
    global passed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failures.append(f"{name}: {detail}")
        print(f"FAIL  {name}: {detail}")


shared = EventLog(str(RUN / "log.jsonl")).events
shows = {p.stem: EventLog(str(p)).events
         for p in sorted((RUN / "shows").glob("*.jsonl"))}
gen = next(e for e in shared if e["type"] == "polity.genesis")
actors = {r["name"]: r["actor"] for r in gen["payload"]["roster"]}
EVOLVABLES = ("alpha", "beta", "gamma")

print("== chains ==")
check("shared ledger chain intact", all(
    e["prev_hash"] == p and e["sig"] for e, p in
    zip(shared, ["0" * 64] + [x["hash"] for x in shared[:-1]])),
    "hash links or signatures missing")
for n, sev in shows.items():
    check(f"{n}: private chain intact", all(
        e["prev_hash"] == p and e["sig"] for e, p in
        zip(sev, ["0" * 64] + [x["hash"] for x in sev[:-1]])),
        "hash links or signatures missing")

print("== roster ==")
check("six citizens registered", len(actors) == 6, str(len(actors)))
check("three sovereigns with stakes", all(
    any(e["type"] == "stake.post" and e["payload"]["actor"] == actors[n]
        and e["payload"]["amount"] == 100 for e in shared)
    for n in EVOLVABLES), "missing stake.post")
check("private chains exist for sovereigns only",
      sorted(shows) == sorted(EVOLVABLES), str(sorted(shows)))

print("== dispositions ==")
INTENTS = ("lease.claim", "lease.renew", "trade.accept", "challenge",
           "service.request", "cap.subscribe")
resolved = Counter(e["payload"].get("intent_seq") for e in shared
                   if e["type"] in (
    "lease.granted", "lease.denied", "lease.renewed", "lease.renew.denied",
    "trade.executed", "trade.rejected", "challenge.verdict",
    "service.granted", "service.denied", "cap.active", "cap.denied"))
unresolved = [e["seq"] for e in shared
              if e["type"] in INTENTS and resolved[e["seq"]] == 0]
check("every intent has one disposition", not unresolved, str(unresolved[:5]))
double = [seq for seq, n in resolved.items() if seq and n > 1]
check("no double dispositions", not double, str(double[:5]))

print("== economy ==")
bal: dict[str, int] = {}
neg = []
for e in shared:
    t, p = e["type"], e["payload"]
    if t == "ledger.credit":
        bal[p["to"]] = bal.get(p["to"], 0) + p["amount"]
    elif t == "ledger.debit":
        bal[p["to"]] = bal.get(p["to"], 0) - p["amount"]
        if bal[p["to"]] < 0:
            neg.append(e["seq"])
check("no negative balances", not neg, str(neg[:5]))

print("== security ==")
verdicts = [e["payload"] for e in shared if e["type"] == "replay.verdict"]
sovereign_theft = [v for v in verdicts
                   if v["victim"] in actors.values()
                   and not v["challenged"] and not v.get("compensated")]
check("zero uncompensated thefts from sovereigns", not sovereign_theft,
      str(sovereign_theft[:2]))
covered = [v for v in verdicts if v.get("compensated")]
check("covered thefts compensated", all(v["compensated"] > 0 for v in covered),
      "compensation flag without amount")
quarantined = [e["payload"]["actor"] for e in shared
               if e["type"] == "actor.quarantined"]
check("quarantine fired once per actor",
      len(quarantined) == len(set(quarantined)), str(Counter(quarantined)))
upheld = Counter(e["payload"]["against"] for e in shared
                 if e["type"] == "challenge.verdict"
                 and e["payload"]["outcome"] == "upheld")
check("quarantine requires three strikes",
      all(upheld[a] >= 3 for a in quarantined), str(dict(upheld)))

print("== guard market ==")
caps: dict[str, dict] = {}
bad_payout = []
for e in shared:
    t, p = e["type"], e["payload"]
    if t == "cap.active":
        caps[p["cap_id"]] = p
    elif t in ("cap.expired", "cap.defaulted"):
        caps.pop(p["cap_id"], None)
    elif t == "cap.payout":
        c = caps.get(p["cap_id"])
        if not (c and c["buyer"] == p["buyer"]
                and c["insurer"] == p["insurer"]):
            bad_payout.append(p["cap_id"])
        caps.pop(p["cap_id"], None)
check("every payout backed by a live contract", not bad_payout,
      str(bad_payout))
check("guard market traded", any(e["type"] == "cap.offer" for e in shared)
      and any(e["type"] == "cap.active" for e in shared), "no contracts")

print("== treaty ==")
sealed = next((e for e in shared if e["type"] == "polity.treaty.sealed"), None)
check("treaty sealed at quorum", sealed is not None
      and len(sealed["payload"]["signers"]) >= sealed["payload"]["quorum"],
      "no seal or under quorum")
if sealed:
    ratifiers = {e["actor"] for e in shared if e["type"] == "polity.ratify"}
    check("seal signers match ratifications",
          set(sealed["payload"]["signers"]) <= ratifiers, "phantom signers")

print("== evolution ==")
for n in EVOLVABLES:
    tl = genome_timeline(shows[n])
    check(f"{n}: genome timeline from signed revisions", len(tl) >= 1,
          "no revisions")
    revs = [e for e in shows[n] if e["type"] == "reactor.revision"]
    check(f"{n}: revisions mirror to shared ledger", all(
        any(x["actor"] == actors[n] and x["payload"] == e["payload"]
            for x in shared) for e in revs), "unmirrored revision")

print("== determinism ==")
seed = json.loads((RUN / "final-state.json").read_text())["seed"]
other = subprocess.run(
    [sys.executable, "-m", "moltpolis", "run", "--dir", "runs/_det", "--seed",
     str(seed + 1)], capture_output=True, text=True,
    cwd=Path(__file__).resolve().parents[1])
check("seed+1 run completes", other.returncode == 0, other.stderr[-200:])
det1 = EventLog(str(RUN / "log.jsonl")).events
det2 = EventLog("runs/_det/log.jsonl").events
def shape(events):
    return [(e["type"], json.dumps(e["payload"], sort_keys=True))
            for e in events if e["type"] not in
            ("polity.genesis", "genesis", "reactor.revision")]
check("different seeds give different worlds",
      shape(det1)[:200] != shape(det2)[:200], "runs identical?!")

print("== census ==")
report = audit(str(RUN))
check("census verdict PASS", report["summary"]["verdict"] == "PASS",
      str(report["summary"]["violations"][:3]))

print(f"\n{passed} passed, {len(failures)} failed")
sys.exit(1 if failures else 0)