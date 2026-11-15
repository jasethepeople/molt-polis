"""run.py — drives the Living Commonwealth and produces every artifact.

One shared polity ledger (log.jsonl) + one private molt-show chain per
citizen (shows/<name>.jsonl). Evolution runs per-citizen at staggered
ticks: each candidate genome is tested by cloning the ENTIRE polis state
(all citizens, all balances, all contracts) into an isolated sandbox and
replaying the remaining trajectory with only that citizen's rules
swapped. Selection is fitness-gated with a zero-new-theft invariant.
"""
from __future__ import annotations

import json
from pathlib import Path

from .citizen import Citizen
from .evolution import Evolver
from .polity import (CITIZENS, EVOLVABLES, TICKS, TREATY_TICK, Polity)
from .ruleset import describe_change
from sovzero.core import EventLog
from sovzero.identity import IdentityStore

GENESIS_ENERGY = 260
GENESIS_STAKE = 100
OTHER_ENERGY = 200
EVOLUTION_TICKS = {"alpha": (25, 55), "beta": (30, 60), "gamma": (35, 65)}


def make_runtime(seed: int, run_dir: Path):
    log = EventLog(str(run_dir / "log.jsonl"))
    shows = {name: EventLog(str(run_dir / "shows" / f"{name}.jsonl"))
             for name in EVOLVABLES}
    identities = IdentityStore(str(run_dir / "keys.json"))
    polis = Polity(log, identities, seed)
    citizens = [Citizen(name, log, shows[name], identities,
                        GENESIS_ENERGY, GENESIS_STAKE)
                for name in EVOLVABLES]
    return polis, citizens


def drive_tick(polis: Polity, citizens: list[Citizen], t: int) -> None:
    """One tick: world step -> citizens react -> adjudication -> reflection."""
    evs = polis.step(t)
    n0 = len(polis.log.events)
    for c in citizens:
        c.observe(evs)
    polis.adjudicate(t)
    post = polis.log.events[n0:]
    for c in citizens:
        c.observe(post)


def run(seed: int = 7, dir_name: str = "runs/default", verbose: bool = False):
    run_dir = Path(dir_name)
    (run_dir / "shows").mkdir(parents=True, exist_ok=True)
    polis, citizens = make_runtime(seed, run_dir)

    polis.genesis()
    genesis_evs = list(polis.log.events)
    for name, energy, stake in (("alpha", GENESIS_ENERGY, GENESIS_STAKE),
                                ("beta", GENESIS_ENERGY, GENESIS_STAKE),
                                ("gamma", GENESIS_ENERGY, GENESIS_STAKE),
                                ("merchant", OTHER_ENERGY, 0),
                                ("reaver", OTHER_ENERGY, 0),
                                ("usurper", OTHER_ENERGY, 0)):
        polis.admit(name, energy, stake)
    for c in citizens:
        c.genesis(polis.log.events[0]["hash"], seed)
        c.observe(list(polis.log.events))

    evolvers = {name: Evolver(seed) for name in EVOLVABLES}
    for t in range(1, TICKS + 1):
        drive_tick(polis, citizens, t)
        for c in citizens:
            if t in EVOLUTION_TICKS[c.name]:
                rep = evolvers[c.name](
                    polis, citizens, c.name, t,
                    {"ticks": TICKS, "pop_size": 6})
                if verbose:
                    tag = (f"adopted gen {rep['generation']} "
                           f"(fit {rep['base_fitness']}->{rep['adopted_fitness']})"
                           if rep["adopted"] else
                           f"gen {rep['generation']} kept incumbent "
                           f"(fit {rep['base_fitness']})")
                    print(f"  evolution {c.name} @ tick {t}: {tag}")
        if verbose and t % 20 == 0:
            energies = {c.name: polis.energy.get(c.actor, 0)
                        for c in citizens}
            print(f"tick {t:3d}: {energies} treaty={bool(polis.treaty)}")

    # ---- artifacts ----------------------------------------------------------
    final = {
        "seed": seed,
        "ticks": TICKS,
        "treaty": polis.treaty,
        "state": {c.name: c.final_state() for c in citizens},
        "world": polis.snapshot(TICKS),
        "fitness": {c.name: fitness_of(polis, c) for c in citizens},
        "evolutions": {c.name: c.evolutions for c in citizens},
        "genesis": genesis_evs[0]["hash"],
    }
    (run_dir / "final-state.json").write_text(json.dumps(final, indent=2))
    return polis, citizens


def fitness_of(polis: Polity, citizen: Citizen) -> int:
    m = polis.citizen_metrics(citizen.actor)
    return citizen.reactor.fitness(
        m, polis.citizen_stolen(citizen.actor),
        polis.citizen_denied(citizen.actor),
        polis.citizen_slashed(citizen.actor),
        polis.open_leases(citizen.actor))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--dir", default="runs/default")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    polis, citizens = run(args.seed, args.dir, args.verbose)
    treaty = polis.treaty
    print(f"run complete -> {args.dir}")
    for c in citizens:
        print(f"  {c.name:9s} fitness {fitness_of(polis, c):6d} "
              f"energy {polis.energy.get(c.actor, 0):5d} "
              f"stake {polis.stakes.get(c.actor, 0):3d} "
              f"leases {polis.open_leases(c.actor):2d} "
              f"genome_gens {sum(1 for e in c.show.events if e['type'] == 'reactor.revision') - 1}")
    print(f"  treaty: {'SEALED quorum ' + str(treaty['signers']) if treaty else 'FAILED'}")
    print(f"  quarantined: {sorted(polis.quarantined) or 'none'}")


if __name__ == "__main__":
    main()