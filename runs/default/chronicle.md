# Chronicle — the Living Commonwealth (molt-polis)

*Rendered from the shared polity ledger and every citizen's private molt-show chain by `molt-show chronicle`.*

## I. Genesis

- **Polity genesis** — seq `#0`, hash `b4ab0b7840cc`, seed `7`, 80 ticks, 16 resource nodes.
- **Roster**: `alpha` (sovereign), `beta` (sovereign), `gamma` (sovereign), `merchant` (scripted), `reaver` (scripted), `usurper` (scripted)
- **Institutions**: staked citizenship (100 energy posted by each sovereign, slashed on protocol violations), a guard market (theft insurance between mutually distrusting agents, enforced by the kernel), and a treaty requiring a 4-signature quorum.

## II. The arc, act by act

**The land rush.** It opens at seq `#28` — `alpha` takes the first grant. Over the run: alpha 6, merchant 6, beta 6, gamma 2, usurper 2 grants; 26 bids denied — the rotated fair queue spreads the wins that first-come-first-served would have hoarded.

**The replay war.** `reaver` mounts 9 replay attacks. Citizens challenge at the kernel's security pass; 7 challenges are upheld, and after the third strike the thief is quarantined at seq `#600`. 2 attack(s) slip through unchallenged — both against the merchant, who has no challenge reflex — and both are made whole by guard payouts. Net stolen from the sovereigns: **0 energy**.

**The guard market.** 21 signed offers (beta 13, gamma 5, alpha 3), 11 subscriptions, 2 payouts — paid by gamma (33 energy). Insurance between agents who cannot read each other's code, enforced by the kernel itself: the premium is priced against the thief's strike count, and the policy pays out without any trust at all.

## III. The three lineages

### `alpha`
- genesis seq `#0` — key `e84c7bad5e31…`, stake 100
- 2 evolution cycles: 12 mutants tested in sandboxed replays of the remaining trajectory, 0 adopted by signed revision — the incumbent kept its crown every time.

### `beta`
- genesis seq `#0` — key `0ee89ffa3a24…`, stake 100
- revision gen 1 at seq `#42` (tick 30): evolution: acquire-guard.max_held: 1→0; sell-guard.reserve: 120→121; claim-nodes.min_yield: 5→4
- revision gen 2 at seq `#82` (tick 60): evolution: accept-fair-trades.min_give: 18→21; claim-nodes.min_yield: 4→6; renew-leases.renew_duration: 10→13
- 2 evolution cycles: 12 mutants tested in sandboxed replays of the remaining trajectory, 2 adopted by signed revision.

### `gamma`
- genesis seq `#0` — key `81451526955d…`, stake 100
- revision gen 1 at seq `#37` (tick 35): evolution: renew-leases.renew_reserve: 58→55; renew-leases.renew_lead: 3→2; sell-guard.max_open: 3→1
- 2 evolution cycles: 12 mutants tested in sandboxed replays of the remaining trajectory, 1 adopted by signed revision.

## IV. The treaty

At tick 70 the dividend treaty is sealed: 4 distinct signatures — `reaver`, `alpha`, `beta`, `gamma`. Non-signers: `merchant`, `usurper` — the usurper dissents on principle; the merchant simply never learned to vote. Dividends flow from tick 71.

## V. Final standings

| citizen | energy | stake | leases | fitness-relevant |
| --- | --- | --- | --- | --- |
| `alpha` | 2145 | 100 | 6 | quarantined: no |
| `beta` | 1766 | 100 | 6 | quarantined: no |
| `gamma` | 1313 | 100 | 2 | quarantined: no |
| `merchant` | 472 | 0 | 1 | quarantined: no |
| `reaver` | 233 | 0 | 0 | quarantined: yes |
| `usurper` | 532 | 0 | 1 | quarantined: no |

**Civilization totals**: 45 trades, 15 services acquired, 2 guard payouts, 0 stake slashes, 7 challenge verdicts — 1610 signed events on the shared chain.

*End of chronicle. Every number above is re-derivable from the two families of chains — that is the point.*

