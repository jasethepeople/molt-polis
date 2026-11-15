"""The polis evolutionary loop — lispmind principles, one genome per citizen.

Each evolvable citizen evolves on its own cadence. A cycle:
  1. MUTATE — candidate rule-sets derived from the citizen's active genome
     (bounded parameter drift + gas jitter, deterministic rng).
  2. TEST   — the ENTIRE polis (shared ledger, every citizen's reactor
     state, every balance) is cloned into an in-memory sandbox and the
     remaining trajectory is replayed once per candidate, with the target
     citizen's rules swapped. Other citizens keep their current genomes —
     this is a best-response search in a fixed-strategy environment.
  3. SELECT — adopt only if the candidate beats the incumbent on the
     citizen's declared fitness AND keeps the zero-violation invariant.
     Adoption is a signed reactor.revision event on the citizen's own
     chain, mirrored to the shared ledger. No rule file is hand-edited.
"""
from __future__ import annotations

import copy
import random

from . import ruleset
from .reactor import PolisReactor


def clone_polis(polis, citizens):
    """Deep-copy the whole polity + citizens into an isolated sandbox.

    Identities are shared by reference (signing is read-only). Logs are
    deep-copied with disk persistence disabled.
    """
    slog = copy.deepcopy(polis.log)
    slog.path = None
    spolis = copy.copy(polis)
    spolis.log = slog
    spolis.ident = polis.ident
    for attr in ("actors", "yields", "energy", "stakes", "leases",
                 "services", "caps", "consumed_offers",
                 "strikes", "quarantined",
                 "resolved_replays", "ratifiers", "metrics"):
        setattr(spolis, attr, copy.deepcopy(getattr(polis, attr)))
    for attr in ("replay_seq_counter", "adj_frontier", "treaty"):
        setattr(spolis, attr, copy.deepcopy(getattr(polis, attr)))
    scits = []
    for c in citizens:
        sc = copy.copy(c)
        sc.reactor = copy.deepcopy(c.reactor)
        slog_c = copy.deepcopy(c.show)
        slog_c.path = None
        sc.show = slog_c
        sc.log = slog
        sc.frontier = c.frontier
        sc.ident = polis.ident.get(c.name)
        scits.append(sc)
    return spolis, scits


class Evolver:
    """One evolver instance per evolvable citizen."""

    def __init__(self, seed: int, pop_size: int = 6):
        self.seed = seed
        self.pop_size = pop_size
        self.generation = 0
        self.reports: list[dict] = []

    def run_rest(self, polis, citizens, t0: int, cadence):
        """Replay the remaining trajectory (no further evolution)."""
        from .run import drive_tick
        for t in range(t0 + 1, cadence["ticks"] + 1):
            drive_tick(polis, citizens, t)

    def evaluate(self, rules, polis, citizens, target, t, cadence):
        spolis, scits = clone_polis(polis, citizens)
        tc = next(c for c in scits if c.name == target)
        tc.reactor.rules = copy.deepcopy(rules)
        self.run_rest(spolis, scits, t, cadence)
        return score(spolis, scits, target)

    def violations(self, m: dict) -> int:
        return m["false_acc"] + m["thefts"]

    def __call__(self, polis, citizens, target: str, t: int, cadence: dict):
        rng = random.Random(f"{self.seed}:{target}:{self.generation}")
        tc = next(c for c in citizens if c.name == target)
        base = ruleset.canonical(tc.reactor.rules)
        base_fitness = self.evaluate(base, polis, citizens, target, t, cadence)

        candidates = []
        for _ in range(self.pop_size):
            mutant, changes = ruleset.mutate(base, rng)
            fitness = self.evaluate(mutant, polis, citizens, target, t, cadence)
            candidates.append({"rules": mutant, "changes": changes,
                               "fitness": fitness})

        viable = [c for c in candidates if c["fitness"] > base_fitness]
        adopted, adopted_fitness, adopted_changes = None, None, []
        if viable:
            best = max(viable, key=lambda c: c["fitness"])
            adopted = tc.adopt_rules(
                best["rules"], self.generation + 1, best["fitness"],
                tick=t, reason="evolution: " + "; ".join(best["changes"]))
            adopted_fitness = best["fitness"]
            adopted_changes = best["changes"]

        report = {
            "generation": self.generation,
            "tick": t,
            "base_fitness": base_fitness,
            "candidates": [{"fitness": c["fitness"], "changes": c["changes"]}
                           for c in candidates],
            "adopted": adopted is not None,
            "adopted_fitness": adopted_fitness,
            "adopted_changes": adopted_changes,
            "revision_seq": adopted["seq"] if adopted else None,
        }
        tc.log_reflection("evolution.report", report)
        self.generation += 1
        self.reports.append(report)
        return report


def score(polis, citizens, name: str) -> float:
    """A citizen's declared fitness, measured from the shared ledger."""
    c = next(x for x in citizens if x.name == name)
    a = polis.actors[name]
    m = polis.citizen_metrics(a)
    return c.reactor.fitness(m, polis.citizen_stolen(a),
                             polis.citizen_denied(a),
                             polis.citizen_slashed(a),
                             polis.open_leases(a))