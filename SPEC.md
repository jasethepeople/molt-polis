# molt-polis SPEC — events, institutions, and invariants

Extends `Projects/sovereign-agent-zero/SPEC.md` (molt-core/1.0) with the
polity layer. Same canonical-JSON hashing, same Ed25519 signing, same
append-only discipline: every event carries `prev_hash`, `seq`, `ts`,
`actor`, `type`, `payload`, `hash`, `pub`, `sig`.

## Two families of chains

- **The shared polity ledger** (`log.jsonl`) — one hash-chained ledger with
  every event of every actor. The citizen's *public voice*.
- **Private molt-show chains** (`shows/<name>.jsonl`) — one per sovereign.
  Contains the citizen's genesis, its reactor revisions, its evolution
  reports, and a byte-identical mirror of every event it signs on the shared
  ledger. molt-census proves the two families agree.

## Event vocabulary (beyond molt-core)

Polity (signed by `sys`):

- `polity.genesis` — seed, ticks, node yields, roster (name → actor id),
  quorum, treaty parameters, kernel version.
- `stake.post` / `stake.slash` — posted citizenship stake; slashes carry a
  reason (false accusation, guard default). Payload actor field names the
  staker; the event itself is signed by `sys`.
- `cap.active` / `cap.expired` / `cap.defaulted` / `cap.payout` — the guard
  contract lifecycle. `cap.payout` carries `claim_seq` (the replay verdict's
  evidence) and the amount actually paid.
- `polity.treaty.proposed` / `polity.treaty.sealed` — the endgame institution;
  the seal lists distinct signers, the dividend, and the from-tick.
- `replay.verdict` — extended with `compensated` (amount paid by a guard, 0
  if uncovered). A theft is a *violation* only when neither challenged nor
  compensated.

Citizen intents (adjudicated by the kernel): `lease.claim`, `lease.renew`,
`trade.accept`, `challenge`, `service.request`, `cap.subscribe`,
`polity.ratify`. Non-intent citizen emissions: `cap.offer`.

## Kernel rules

1. **Security outranks land.** Adjudication runs challenges, trades,
   services, subscriptions and ratifications in event order first; land
   claims are served second, in a **rotated fair queue**
   (`(registration_index + tick) mod |roster|`, ties by seq).
2. **Proposals are multi-fulfillable.** A trade proposal may be accepted by
   any number of citizens, each paying `want` and receiving `give` while the
   proposer is solvent. Guard offers are single-buyer (`consumed_offers`).
3. **Guards pay without trust.** On an unchallenged theft of a covered buyer,
   the kernel debits the insurer `min(amount, insurer energy)` and credits
   the victim; a shortfall triggers `cap.defaulted` and a 25-energy slash.
4. **Quarantine needs three strikes**, and the `actor.quarantined` event
   fires exactly once per actor.
5. **The treaty seals at exactly the configured quorum** of distinct
   ratifying actors for the live proposal hash; dividends credit every
   non-quarantined citizen from the next tick.

## Reactor extensions (molt-core/1.0+polis)

- New facts: `guards`, `sold_guards`, `stake`, `treaty`, plus
  `replay.victim` on `replay.claim` events.
- New operator: `mod` (divisibility cadence).
- Value resolution: `"@self"` in a condition value resolves to the reactor's
  own actor id.
- Template fact: `ev_cap_id` → `cap-<actor-fingerprint>-<trigger seq>`, so
  two citizens offering in the same tick can never collide on a contract id.
- Fitness (declared at genesis; the evolver optimizes it):
  `energy + 40·leases + 10·services + stake + 5·guards
   − 3·denied − 8·stolen − 4·slashed − 60·violations − 2·gas_exhausted`,
  where `violations` counts false accusations and *uncompensated* thefts.

## Census claims (molt-census)

Exit code non-zero on any failure. Re-derived from the chains alone:

1. Chain integrity (hashes + signatures) of the shared ledger and every
   private log.
2. Every citizen event is signed by the key minted in its genesis.
3. Mirror fidelity: every private event exists identically on the shared
   ledger.
4. Genome provenance: the timeline of signed revisions; the census rebuilds
   each citizen's genome from the shared ledger's mirrored revisions.
5. Deterministic replay: a fresh reactor, fed the shared ledger (skipping the
   citizen's own events) under that genome timeline, reproduces every
   emission bit-for-bit.
6. Conservation: no balance ever goes negative; every intent has exactly one
   sys disposition referencing it (`intent_seq`).
7. Zero-violation: no uncompensated theft, no false accusation.
8. Civilization invariants: quarantine requires three upheld verdicts; every
   guard payout/default is backed by a live contract and (on default) a
   slash; the treaty's signers are registered, distinct, and quorum-sized.

## Determinism

No RNG. All stochastic choices are `h(seed, salt, mod) = sha256(seed:salt) mod
mod`. A run is a pure function of `(seed, ticks, genomes)`; the only
cross-run differences are freshly-minted keys and wall-clock `ts` inside the
hashes. Evolution is deterministic per citizen (`Random(f"{seed}:{name}:{gen}")`).
