# AGENTS.md — Molt Polis

Project-specific implementation rules for `Projects/molt-polis/`.

## What this is

The fourth molt challenge: a living commonwealth of sovereign, self-evolving
agents sharing one deterministic economy. Built on the sovzero primitives
(`Projects/sovereign-agent-zero/`), imported via the path shim in
`moltpolis/__init__.py`. Read `README.md` for the walkthrough and `SPEC.md`
for the event vocabulary and kernel rules.

## Non-negotiable invariants

- **No rule file is ever hand-edited after genesis.** Every genome change is
  a signed `reactor.revision` on the citizen's private chain, mirrored to the
  shared ledger, installed by the citizen's own evolver.
- **Every event is signed.** The shared ledger carries each actor's own
  Ed25519 signature; `sys` signs only its own adjudications.
- **The census trusts no live process.** It re-derives everything from
  `log.jsonl` and `shows/*.jsonl` alone, and its verdict gates (`exit 1` on
  FAIL). If you add an event kind, extend `census.py`, `chronicle.py`, the
  observatory, and `tests/test_polis.py` in the same change.
- **Security outranks land.** Challenges must never wait behind land grants —
  a delayed challenge is a theft. The rotated fair queue applies to
  `lease.claim` only.
- **A covered theft is not a violation.** The census counts a theft as a
  violation only when it is neither challenged nor compensated. Do not
  weaken this: uncompensated thefts and false accusations fail the census.
- **Determinism is the contract.** No RNG, no wall-clock in game logic (the
  `ts` field is bookkeeping only). Sandbox clones must deep-copy all mutable
  polity state; the checklist of attributes lives in
  `evolution.clone_polis` — extend it when `Polity` grows state.

## File conventions

- `runs/<dir>/` holds all artifacts of a run; `keys.json` is 0600 and must
  never be committed, moved, or published. Zips of this project must exclude
  `keys.json`, `keys/`, `__pycache__/`, and `:memory:` files.
- Canonical JSON everywhere (`sovzero.core.canonical`); digests are
  sha256 of canonical bytes.
- Private shows mirror shared events byte-identically — `Citizen._record`
  appends the same payload to both chains; never let them diverge.

## Testing

`python3 tests/test_polis.py` from the project root (27 checks, exit code
non-zero on failure). It covers chain integrity, roster/stakes, intent
dispositions, conservation, security (zero uncompensated thefts, quarantine
exactly once at three strikes), the guard market, the treaty quorum, genome
timelines, and determinism (a second run must match modulo identity).

## Commands

```
python3 -m moltpolis run --seed 7 -v          # full run (~2 min)
python3 -m moltpolis census --dir runs/default
python3 -m moltpolis chronicle --dir runs/default
python3 -m moltpolis serve --dir runs/default --port 8600
```
