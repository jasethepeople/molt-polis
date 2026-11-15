"""A citizen of the polis: its own Ed25519 identity, its own molt-show
chain (its consciousness), its own evolving reactor — and a public voice
as signed events on the shared polity ledger.

The citizen's private log mirrors every event it signs on the shared
ledger (emissions, revisions, reports). molt-census later proves the two
chains agree, event for event.
"""
from __future__ import annotations

import copy

from .reactor import PolisReactor
from . import ruleset
from sovzero.core import EventLog, event_hash
from sovzero.identity import Identity, IdentityStore


class Citizen:
    def __init__(self, name: str, log: EventLog, show: EventLog,
                 identities: IdentityStore, energy: int, stake: int):
        self.name = name
        self.ident: Identity = identities.get(name)
        self.actor = f"citizen:{name}@{self.ident.fingerprint}"
        self.log = log          # shared polity ledger
        self.show = show        # private molt-show chain
        self.frontier = 0       # last shared-log seq fed to the reactor
        self.evolutions: list[dict] = []
        self.reactor = PolisReactor([], self.actor)
        self.energy0, self.stake0 = energy, stake

    # ---- genesis ----------------------------------------------------------
    def genesis(self, world_genesis_hash: str, seed: int) -> dict:
        rules = ruleset.initial_rules(self.actor, self.name, seed)
        payload = {"allocation": {"energy": self.energy0, "stake": self.stake0},
                   "identity_pub": self.ident.pub_hex,
                   "world_genesis_hash": world_genesis_hash,
                   "kernel": "molt-core/1.0+polis",
                   "genome_rev": 0}
        self._record("genesis", payload)
        self.reactor.rules = rules
        self.reactor.stake = self.stake0
        self._record("reactor.revision",
                     {"gen": 0, "rules": rules, "at_world_seq": 0,
                      "reason": "genesis genome", "identity_pub":
                      self.ident.pub_hex})
        return payload

    # ---- observe: react to shared events, speak, and mirror ---------------
    def observe(self, events: list[dict]) -> list[dict]:
        emitted = []
        for ev in events:
            if ev["seq"] <= self.frontier:
                continue
            self.frontier = ev["seq"]
            for out in self.reactor.observe(ev):
                payload = {**out["args"], "ref_seq": ev["seq"],
                           "ref_hash": ev["hash"]}
                self._record(out["type"], payload)
                emitted.append({"type": out["type"], "payload": payload})
        return emitted

    # ---- governance: the only way rules ever change ------------------------
    def adopt_rules(self, rules: list[dict], gen: int, fitness,
                    tick: int, reason: str) -> dict:
        payload = {"gen": gen, "rules": rules, "at_world_seq": tick,
                   "reason": reason}
        if fitness is not None:
            payload["simulated_fitness"] = fitness
        ev = self._record("reactor.revision", payload)
        self.reactor.rules = copy.deepcopy(rules)
        return ev

    def log_reflection(self, etype: str, payload: dict) -> dict:
        return self._record(etype, payload)

    # ---- internals ---------------------------------------------------------
    def _record(self, etype: str, payload: dict) -> dict:
        ev = self.log.append(self.actor, etype, payload, signer=self.ident)
        self.show.append(self.actor, etype, payload, signer=self.ident)
        return ev

    def final_state(self) -> dict:
        r = self.reactor
        return {"name": self.name, "actor": self.actor,
                "pub": self.ident.pub_hex,
                "energy": r.energy, "stake": r.stake,
                "leases": sorted(r.leases), "guards": len(r.guards),
                "sold_guards": len(r.sold),
                "services": len(r.services),
                "rules": len(r.rules), "gas_exhausted": r.gas_exhausted}


def active_genome(show_events: list[dict], at_tick: int) -> list[dict]:
    """Genome timeline: the latest signed revision valid at `at_tick`."""
    rules, gen = None, 0
    for ev in show_events:
        if ev["type"] == "reactor.revision" \
                and ev["payload"].get("at_world_seq", 0) <= at_tick \
                and isinstance(ev["payload"].get("rules"), list):
            rules, gen = ev["payload"]["rules"], ev["payload"].get("gen", 0)
    return rules


def genome_timeline(show_events: list[dict]) -> list[dict]:
    return [{"gen": ev["payload"].get("gen", 0),
             "at_world_seq": ev["payload"].get("at_world_seq", 0),
             "rules": ev["payload"]["rules"],
             "event_seq": ev["seq"],
             "event_hash": ev["hash"]}
            for ev in show_events
            if ev["type"] == "reactor.revision"
            and isinstance(ev["payload"].get("rules"), list)]


def revision_hash(show_events: list[dict]) -> str | None:
    for ev in show_events:
        if ev["type"] == "reactor.revision":
            return event_hash(ev["payload"]["rules"])
    return None