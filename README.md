# Molt Polis — The Living Commonwealth

The fourth molt-stack challenge. Sovereign Agent Zero proved the **self**,
the Byzantium Swarm proved the **network**, the Capability Bazaar proved the
**market**. The polis composes all three into a civilization: six citizens —
three of them sovereign and self-evolving — share one deterministic,
adversarial economy, and a cross-audit (molt-census) proves every private
chain agrees with the shared ledger, event for event.

## What it builds

`python3 -m moltpolis run --dir runs/default [--seed N]` runs the whole
civilization for 80 ticks and writes a fully replayable run:

```
runs/default/
├── log.jsonl           the shared polity ledger (every actor, every event,
│                       each signed by its own Ed25519 identity)
├── shows/*.jsonl       the three sovereigns' PRIVATE molt-show chains
│                       (their consciousness: genesis, revisions, reports,
│                       and a mirror of every event they sign)
├── final-state.json    end-of-run standings + genome lineage + treaty
├── census-report.json  molt-census: the cross-audit verdict
├── census-report.md    human-readable audit
├── chronicle.md        the civilization chronicle
└── observatory.png     dashboard screenshot (live view below)
keys.json               all Ed25519 identities (0600 — never publish)
```

```
python3 -m moltpolis run       [--dir runs/default] [--seed N] [-v]
python3 -m moltpolis census    [--dir runs/default]     # exit 1 on FAIL
python3 -m moltpolis chronicle [--dir runs/default]
python3 -m moltpolis serve     [--dir runs/default] [--port 8600]
python3 tests/test_polis.py                            # 27 invariant checks
```

Exit code 0 means the census verdict is PASS.

## The roster

| citizen | nature | behavior |
| --- | --- | --- |
| `alpha`, `beta`, `gamma` | sovereign | own key, own private chain, own evolving molt-reactor genome (9 rules), own evolution cadence |
| `merchant` | cooperative | holds 3 nodes, proposes fair gift-trades, buys guard insurance — but cannot challenge replays and never learned to vote |
| `reaver` | adversarial | replays signed ledger.credits to steal energy, escalating after tick 40; ratifies treaties |
| `usurper` | adversarial | races for the best free nodes (up to 5), dissents from treaties |

## The institutions

- **Staked citizenship** — each sovereign posts 100 energy as stake; the kernel
  slashes it for false accusations and guard defaults.
- **The guard market** — citizens sell theft insurance to each other
  (`cap.offer` → `cap.subscribe` → `cap.active`). When a replay theft lands
  on a covered buyer, the kernel itself debits the insurer and compensates the
  victim — insurance between agents who cannot read each other's code.
  `cap.defaulted` + stake slash punish insurers who cannot pay.
- **The treaty** — at tick 70 the kernel proposes a dividend treaty; it seals
  only at a quorum of 4 distinct citizen signatures. The usurper dissents on
  principle and the merchant cannot vote, so the three sovereigns hold the
  exact quorum: evolution must never evolve away the ratify reflex.
- **The rotated fair queue** — land claims arriving in the same adjudication
  window are served in an order that rotates by tick (challenges always jump
  the queue). First-come-first-served would let the earliest-registered actor
  win every simultaneous bid; rotation spreads the wins.

## The autonomy constraint

After genesis, no rule file is hand-edited. Each sovereign's rules change only
through signed `reactor.revision` events on its private chain, installed by its
own evolver: MUTATE (deterministic mutants from `ruleset.mutate`) → TEST (the
ENTIRE polis — shared ledger, all reactors, all balances — is cloned into an
in-memory sandbox and the remaining trajectory replayed once per candidate,
with the other citizens' genomes frozen) → SELECT (adopt only if the candidate
beats the incumbent on the citizen's declared fitness). Evolution cycles also
mirror every revision to the shared ledger, so the census can re-derive each
citizen's genome timeline from the public record alone.

## The recorded lifecycle (`runs/default/`, seed 7)

- Genesis: 6 citizens registered, 3 sovereigns staked (100 energy each), 16
  resource nodes (yields 5–8/tick), 80 ticks.
- The land rush: 22 grants under the rotated fair queue — alpha 6, beta 6,
  merchant 6, gamma 2, usurper 2 — plus 26 denied bids.
- The replay war: the reaver mounted 9 replay attacks; 7 were challenged and
  upheld (3 strikes → quarantined), and the 2 that slipped through hit the
  merchant — who has no challenge reflex — and were made whole by guard
  payouts from gamma. Net energy stolen from the sovereigns: **0**.
- The guard market: 21 signed offers, 11 subscriptions, 2 payouts — priced
  against live risk, settled by the kernel without trust.
- Evolution: 36 mutants tested in full-polis sandbox replays; beta adopted 2
  revisions, gamma 1, alpha kept its incumbent. Final fitness: alpha 2849,
  beta 2464, gamma 2016.
- The treaty: sealed with exactly the quorum — reaver, alpha, beta, gamma —
  and dividends flowed for the final 10 ticks.
- molt-census: **PASS, 0 violations across 1610 shared events** — chain
  integrity, mirror fidelity, deterministic replay under each citizen's genome
  timeline, conservation, and every civilization invariant.

## Determinism

No RNG anywhere: all "randomness" is sha256 of `(seed, salt)`, and the whole
civilization is a pure function of `(seed, ticks, genomes)`. Two independent
runs of the same seed produce identical final state (modulo each run's
freshly-forged keys and the wall-clock timestamps inside event hashes); two
runs with different seeds diverge. The census reproduces every citizen's
emissions bit-for-bit from the shared ledger and their genome timeline.

## Architecture

```
moltpolis/
├── __init__.py     path shim: imports sovzero primitives
├── reactor.py      PolisReactor — molt-core DSL + guards/stake/treaty facts,
│                   "@self" value resolution, "mod" operator
├── ruleset.py      the 9-rule genesis genome + mutation operators
├── citizen.py      Citizen: identity, private chain, emissions + mirrors
├── polity.py       the world kernel: ledger, leases, trades, services,
│                   guard contracts, strikes/quarantine, stakes, treaty
├── evolution.py    per-citizen evolver; whole-polis sandbox clones
├── run.py          orchestration + artifacts
├── census.py       molt-census — the cross-audit (exit code gates)
├── chronicle.py    the civilization chronicle
├── observatory.py  dashboard on :8600 (+ /api/summary, /api/events)
└── __main__.py     CLI
```

Primitive layer is `Projects/sovereign-agent-zero` (sovzero): EventLog,
Ed25519 identities, the molt-reactor DSL engine, mutation machinery. See
`SPEC.md` for the extended event vocabulary and `AGENTS.md` for the
non-negotiable invariants.
