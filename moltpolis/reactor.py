"""The polis reactor: molt-core extended with polis facts and templates.

New facts: guards (active contracts bought), sold_guards (contracts sold),
stake (posted stake after slashes), treaty (1 once sealed).
New template fact: ev_cap_id -> "cap-<triggering event seq>".
New op: mod (divisibility cadence). Value resolution: "@self" -> actor id.
"""
from __future__ import annotations

from sovzero.reactor import Reactor, OPS, _lookup, _resolve


OPS2 = dict(OPS)
OPS2["mod"] = lambda a, b: b > 0 and a % b == 0


class PolisReactor(Reactor):
    def __init__(self, rules: list[dict], self_actor: str):
        super().__init__(rules, self_actor)
        self.guards: dict[str, dict] = {}
        self.sold: dict[str, dict] = {}
        self.stake = 0
        self.treaty = False

    # ---- state application (extends molt-core) ---------------------------
    def _apply_state(self, ev: dict):
        super()._apply_state(ev)
        p, t = ev["payload"], ev["type"]
        if t == "lease.granted":
            if p["holder"] == self.self_actor:
                self.leases[p["node"]] = {"until": p["until_tick"],
                                          "yield": p["yield"]}
        elif t == "cap.active":
            cid = p["cap_id"]
            if p["buyer"] == self.self_actor:
                self.guards[cid] = {"until": p["until_tick"],
                                    "premium": p["premium"]}
            elif p["insurer"] == self.self_actor:
                self.sold[cid] = {"until": p["until_tick"],
                                  "premium": p["premium"]}
        elif t in ("cap.expired", "cap.defaulted"):
            cid = p["cap_id"]
            self.guards.pop(cid, None)
            self.sold.pop(cid, None)
        elif t == "stake.slash" and p["actor"] == self.self_actor:
            self.stake -= p["amount"]
        elif t == "polity.treaty.sealed":
            self.treaty = True

    # ---- condition evaluation (extends molt-core) ------------------------
    def _conds_hold(self, conds, params, item, alias) -> bool:
        for c in conds:
            fact = c["fact"]
            if fact == "guards":
                val = len(self.guards)
            elif fact == "sold_guards":
                val = len(self.sold)
            elif fact == "stake":
                val = self.stake
            elif fact == "treaty":
                val = 1 if self.treaty else 0
            else:
                val = _lookup(fact, item, alias)
            ref = params[c["param"]] if "param" in c else c.get("value")
            if isinstance(ref, str) and ref == "@self":
                ref = self.self_actor
            try:
                if not OPS2[c["op"]](val, ref):
                    return False
            except TypeError:
                return False
        return True

    # ---- context (extends molt-core) -------------------------------------
    def _ctx(self, ev: dict) -> dict:
        ctx = super()._ctx(ev)
        if ev["type"] == "replay.claim":
            ctx["replay.victim"] = ev["payload"].get("victim")
        fp = self.self_actor.rsplit("@", 1)[-1][:6]
        ctx["ev_cap_id"] = f"cap-{fp}-{ev['seq']}"
        return ctx

    # ---- fitness (declared at genesis; the evolver optimizes this) -------
    def fitness(self, m: dict, stolen: int, denied: int, slashed: int,
                open_leases: int = 0) -> int:
        violations = m["false_accusations"] + m["thefts"]
        return (self.energy
                + 40 * len(self.leases)
                + 10 * len(self.services)
                + self.stake
                + 5 * len(self.guards)
                - 3 * denied
                - 8 * stolen
                - 4 * slashed
                - 60 * violations
                - 2 * self.gas_exhausted)