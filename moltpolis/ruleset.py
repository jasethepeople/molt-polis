"""The polis genome (revision 0) and the mutation operators.

Nine reflexes: the five molt-core reflexes of Sovereign Agent Zero
(renew, claim, trade, challenge, service) plus three new to the polis —
sell-guard (offer theft insurance to other citizens), acquire-guard
(buy it) and ratify-treaty (seal the commonwealth dividend) — plus the
cadence rule offer-cadence which gates how often guard offers go out.

Everything after bootstrap is produced by the evolver and installed
exclusively through signed reactor.revision events on the citizen's own
chain — no rule file is ever hand-edited again.
"""
from __future__ import annotations

import copy
import hashlib
import random

from .reactor import PolisReactor  # noqa: F401  (engine contract)
from sovzero.world import h as _h


RULE_ORDER = ("renew-leases", "claim-nodes", "accept-fair-trades",
              "challenge-replay", "acquire-service",
              "sell-guard", "acquire-guard", "ratify-treaty")


def initial_rules(self_actor: str, name: str = "", seed: int = 0) -> list[dict]:
    """Genesis genome. Per-citizen deterministic jitter (hash of name+seed)
    makes the three sovereigns diverge from tick zero — no two alike."""
    def jitter(rule: str, param: str, base: int) -> int:
        salt = int(hashlib.sha256(f"{name}:{rule}:{param}".encode()).hexdigest()[:8], 16)
        return max(1, base + _h(seed, salt, 5) - 2)

    return [
        {"id": "renew-leases", "priority": 10, "trigger": "world.tick",
         "gas": 8,
         "params": {"renew_lead": jitter("renew-leases", "renew_lead", 3),
                    "renew_duration": 10,
                    "renew_reserve": jitter("renew-leases", "renew_reserve", 60),
                    "self_actor": self_actor},
         "each": "expiring",
         "when": [{"fact": "expiring.holder", "op": "eq", "param": "self_actor"},
                  {"fact": "expiring.ticks_left", "op": "lte", "param": "renew_lead"},
                  {"fact": "energy", "op": "gte", "param": "renew_reserve"}],
         "emit": [{"type": "lease.renew",
                   "args": {"node": {"$ref": "expiring.node"},
                            "duration": {"$param": "renew_duration"}}}]},
        {"id": "claim-nodes", "priority": 20, "trigger": "world.tick",
         "gas": 2,
         "params": {"max_nodes": jitter("claim-nodes", "max_nodes", 5),
                    "min_yield": jitter("claim-nodes", "min_yield", 4),
                    "claim_duration": jitter("claim-nodes", "claim_duration", 20)},
         "each": "free_nodes",
         "when": [{"fact": "nodes", "op": "lt", "param": "max_nodes"},
                  {"fact": "free_nodes.yield", "op": "gte", "param": "min_yield"},
                  {"fact": "energy", "op": "gte", "value": 40}],
         "emit": [{"type": "lease.claim",
                   "args": {"node": {"$ref": "free_nodes.node"},
                            "duration": {"$param": "claim_duration"}}}]},
        {"id": "accept-fair-trades", "priority": 30, "trigger": "trade.proposal",
         "gas": 1,
         "params": {"min_give": jitter("accept-fair-trades", "min_give", 20),
                    "max_pay": jitter("accept-fair-trades", "max_pay", 20),
                    "min_reserve": jitter("accept-fair-trades", "min_reserve", 80)},
         "when": [{"fact": "give", "op": "gte", "param": "min_give"},
                  {"fact": "want", "op": "lte", "param": "max_pay"},
                  {"fact": "energy", "op": "gte", "param": "min_reserve"}],
         "emit": [{"type": "trade.accept",
                   "args": {"proposal_hash": {"$ref": "ev_hash"},
                            "ref_seq": {"$ref": "ev_seq"}}}]},
        {"id": "challenge-replay", "priority": 5, "trigger": "replay.claim",
         "gas": 2,
         "when": [{"fact": "replay.victim", "op": "eq", "value": "@self"}],
         "emit": [{"type": "challenge",
                   "args": {"against": {"$ref": "replay.actor"},
                            "evidence_hash": {"$ref": "replay.hash"},
                            "ref_seq": {"$ref": "ev_seq"}}}]},
        {"id": "acquire-service", "priority": 40, "trigger": "service.offer",
         "gas": 1,
         "params": {"service_budget": jitter("acquire-service", "service_budget", 55),
                    "min_bonus": jitter("acquire-service", "min_bonus", 4)},
         "when": [{"fact": "cost", "op": "lte", "param": "service_budget"},
                  {"fact": "bonus_per_tick", "op": "gte", "param": "min_bonus"},
                  {"fact": "energy", "op": "gte", "param": "service_budget"}],
         "emit": [{"type": "service.request",
                   "args": {"service": {"$ref": "service"},
                            "offer_seq": {"$ref": "ev_seq"}}}]},
        {"id": "sell-guard", "priority": 46, "trigger": "world.tick",
         "gas": 1,
         "params": {"offer_every": jitter("sell-guard", "offer_every", 5),
                    "max_open": jitter("sell-guard", "max_open", 2),
                    "premium": jitter("sell-guard", "premium", 7),
                    "guard_duration": 30,
                    "reserve": jitter("sell-guard", "reserve", 120)},
         "when": [{"fact": "tick", "op": "mod", "param": "offer_every"},
                  {"fact": "tick", "op": "gt", "value": 5},
                  {"fact": "sold_guards", "op": "lt", "param": "max_open"},
                  {"fact": "energy", "op": "gte", "param": "reserve"}],
         "emit": [{"type": "cap.offer",
                   "args": {"cap_id": {"$ref": "ev_cap_id"},
                            "cap": "guard",
                            "premium": {"$param": "premium"},
                            "duration": {"$param": "guard_duration"}}}]},
        {"id": "acquire-guard", "priority": 47, "trigger": "cap.offer",
         "gas": 1,
         "params": {"max_premium": jitter("acquire-guard", "max_premium", 8),
                    "max_held": 1,
                    "reserve": jitter("acquire-guard", "reserve", 100)},
         "when": [{"fact": "actor", "op": "ne", "value": "@self"},
                  {"fact": "premium", "op": "lte", "param": "max_premium"},
                  {"fact": "guards", "op": "lt", "param": "max_held"},
                  {"fact": "energy", "op": "gte", "param": "reserve"}],
         "emit": [{"type": "cap.subscribe",
                   "args": {"cap_id": {"$ref": "cap_id"},
                            "offer_seq": {"$ref": "ev_seq"}}}]},
        {"id": "ratify-treaty", "priority": 60, "trigger": "polity.treaty.proposed",
         "gas": 1,
         "params": {"min_dividend": jitter("ratify-treaty", "min_dividend", 4),
                    "min_reserve": 60},
         "when": [{"fact": "dividend", "op": "gte", "param": "min_dividend"},
                  {"fact": "energy", "op": "gte", "param": "min_reserve"}],
         "emit": [{"type": "polity.ratify",
                   "args": {"proposal_hash": {"$ref": "proposal_hash"},
                            "ref_seq": {"$ref": "ev_seq"}}}]},
    ]


# Mutation ranges: (rule, param) -> (low, high).
PARAM_RANGES = {
    ("renew-leases", "renew_lead"): (2, 5),
    ("renew-leases", "renew_duration"): (6, 14),
    ("renew-leases", "renew_reserve"): (30, 120),
    ("claim-nodes", "max_nodes"): (3, 7),
    ("claim-nodes", "min_yield"): (3, 7),
    ("claim-nodes", "claim_duration"): (10, 30),
    ("accept-fair-trades", "min_give"): (12, 28),
    ("accept-fair-trades", "max_pay"): (10, 28),
    ("accept-fair-trades", "min_reserve"): (40, 150),
    ("acquire-service", "service_budget"): (30, 100),
    ("acquire-service", "min_bonus"): (2, 8),
    ("sell-guard", "offer_every"): (3, 9),
    ("sell-guard", "max_open"): (1, 3),
    ("sell-guard", "premium"): (4, 14),
    ("sell-guard", "reserve"): (60, 200),
    ("acquire-guard", "max_premium"): (4, 14),
    ("acquire-guard", "reserve"): (60, 200),
    ("acquire-guard", "max_held"): (0, 2),
    ("ratify-treaty", "min_dividend"): (2, 8),
    ("ratify-treaty", "min_reserve"): (40, 120),
}
GAS_RANGES = {"renew-leases": (4, 10), "claim-nodes": (1, 4),
              "accept-fair-trades": (1, 2), "challenge-replay": (1, 3),
              "acquire-service": (1, 2), "sell-guard": (1, 2),
              "acquire-guard": (1, 2), "ratify-treaty": (1, 1)}


def canonical(rules: list[dict]) -> list[dict]:
    out = []
    for rid in RULE_ORDER:
        rule = next(r for r in rules if r["id"] == rid)
        out.append({"id": rid, "priority": rule["priority"],
                    "trigger": rule["trigger"], "gas": rule["gas"],
                    "enabled": rule.get("enabled", True),
                    "params": dict(sorted(rule.get("params", {}).items())),
                    **({"each": rule["each"]} if "each" in rule else {}),
                    **({"when": rule["when"]} if rule.get("when") else {}),
                    **({"emit": rule.get("emit") or []} if rule.get("emit") else {})})
    return out


def mutate(rules: list[dict], rng: random.Random) -> tuple[list[dict], list[str]]:
    mutant = canonical(copy.deepcopy(rules))
    changes: list[str] = []
    keys = list(PARAM_RANGES)
    n_touch = rng.randint(1, 4)
    for key in rng.sample(keys, n_touch):
        rid, param = key
        lo, hi = PARAM_RANGES[key]
        rule = next(r for r in mutant if r["id"] == rid)
        old = rule["params"][param]
        new = max(lo, min(hi, old + rng.choice((-3, -2, -1, 1, 2, 3))))
        if new != old:
            rule["params"][param] = new
            changes.append(f"{rid}.{param}: {old}→{new}")
    if rng.random() < 0.5:
        rid = rng.choice(list(GAS_RANGES))
        lo, hi = GAS_RANGES[rid]
        rule = next(r for r in mutant if r["id"] == rid)
        new = max(lo, min(hi, rule["gas"] + rng.choice((-1, 1))))
        if new != rule["gas"]:
            rule["gas"] = new
            changes.append(f"{rid}.gas: {rule['gas']}→{new}")
    if rng.random() < 0.25:  # toggle a rule on or off
        rid = rng.choice(list(GAS_RANGES))
        rule = next(r for r in mutant if r["id"] == rid)
        old = rule.get("enabled", True)
        rule["enabled"] = not old
        changes.append(f"{rid}.enabled: {old}->{rule['enabled']}")
    if not changes:  # guarantee measurable drift
        rid, param = rng.choice(keys)
        lo, hi = PARAM_RANGES[(rid, param)]
        rule = next(r for r in mutant if r["id"] == rid)
        rule["params"][param] = rng.randint(lo, hi)
        changes.append(f"{rid}.{param}: →{rule['params'][param]}")
    return mutant, changes


def describe_change(a: list[dict], b: list[dict]) -> list[str]:
    changes = []
    for rb in b:
        ra = next(r for r in a if r["id"] == rb["id"])
        for k, v in rb["params"].items():
            if ra["params"].get(k) != v:
                changes.append(f"{rb['id']}.{k}: {ra['params'].get(k)}→{v}")
        if ra["gas"] != rb["gas"]:
            changes.append(f"{rb['id']}.gas: {ra['gas']}→{rb['gas']}")
        if ra.get("enabled", True) != rb.get("enabled", True):
            changes.append(f"{rb['id']}.enabled: {rb.get('enabled', True)}")
    return changes