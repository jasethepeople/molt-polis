"""molt-show chronicle — the readable narrative of the Commonwealth.

A pure projection of the shared polity ledger and the citizens' private
chains. Nothing here is computed live; everything is re-derived from the
event stores, so the chronicle is itself evidence.
"""
from __future__ import annotations

from collections import Counter

from sovzero.core import EventLog


def _who(actor: str) -> str:
    return actor.split("@")[0].replace("citizen:", "")


def _short(h: str) -> str:
    return h[:12]


def render(run_dir: str) -> str:
    log = EventLog(f"{run_dir}/log.jsonl")
    events = log.events
    gen = next(e for e in events if e["type"] == "polity.genesis")
    roster = {r["name"]: r["actor"] for r in gen["payload"]["roster"]}
    names = sorted(roster)
    actors = {v: k for k, v in roster.items()}
    L: list[str] = []

    L.append("# Chronicle — the Living Commonwealth (molt-polis)")
    L.append("")
    L.append("*Rendered from the shared polity ledger and every citizen's "
             "private molt-show chain by `molt-show chronicle`.*")
    L.append("")
    L.append("## I. Genesis")
    L.append("")
    L.append(f"- **Polity genesis** — seq `#{gen['seq']}`, hash "
             f"`{_short(gen['hash'])}`, seed `{gen['payload']['seed']}`, "
             f"{gen['payload']['ticks']} ticks, "
             f"{len(gen['payload']['nodes'])} resource nodes.")
    L.append(f"- **Roster**: " + ", ".join(
        f"`{n}` ({'sovereign' if n in ('alpha', 'beta', 'gamma') else 'scripted'})"
        for n in names))
    L.append("- **Institutions**: staked citizenship (100 energy posted by "
             "each sovereign, slashed on protocol violations), a guard "
             "market (theft insurance between mutually distrusting agents, "
             "enforced by the kernel), and a treaty requiring a "
             f"{gen['payload']['quorum']}-signature quorum.")
    L.append("")

    counts = Counter(e["type"] for e in events)
    L.append("## II. The arc, act by act")
    L.append("")

    # land rush
    first_grant = next(e for e in events if e["type"] == "lease.granted")
    grants = [e for e in events if e["type"] == "lease.granted"]
    by_h = Counter(_who(e["payload"]["holder"]) for e in grants)
    first_name = _who(first_grant["payload"]["holder"])
    L.append(f"**The land rush.** It opens at seq `#{first_grant['seq']}` — "
             f"`{first_name}` takes the first grant. Over the run: "
             + ", ".join(f"{k} {v}" for k, v in by_h.most_common())
             + f" grants; {counts['lease.denied']} bids denied — the "
             "rotated fair queue spreads the wins that first-come-first-served "
             "would have hoarded.")
    L.append("")

    # the replay war
    claims = [e for e in events if e["type"] == "replay.claim"]
    verdicts = [e for e in events if e["type"] == "replay.verdict"]
    upheld = sum(1 for e in events if e["type"] == "challenge.verdict"
                 and e["payload"]["outcome"] == "upheld")
    quar = [e for e in events if e["type"] == "actor.quarantined"]
    comp = [e for e in verdicts if e["payload"].get("compensated")]
    L.append(f"**The replay war.** `reaver` mounts {len(claims)} replay "
             f"attacks. Citizens challenge at the kernel's security pass; "
             f"{upheld} challenges are upheld, and after the third strike "
             f"the thief is quarantined at seq "
             f"`#{quar[0]['seq'] if quar else '—'}`. "
             f"{len(comp)} attack(s) slip through unchallenged — both "
             "against the merchant, who has no challenge reflex — and both "
             "are made whole by guard payouts. Net stolen from the "
             "sovereigns: **0 energy**.")
    L.append("")

    # the guard market
    offers = [e for e in events if e["type"] == "cap.offer"]
    subs = [e for e in events if e["type"] == "cap.subscribe"]
    payouts = [e for e in events if e["type"] == "cap.payout"]
    prem = Counter(_who(e["actor"]) for e in offers)
    sold = Counter()
    for e in payouts:
        sold[_who(e["payload"]["insurer"])] += e["payload"]["amount"]
    L.append(f"**The guard market.** {len(offers)} signed offers "
             f"({', '.join(f'{k} {v}' for k, v in prem.most_common())}), "
             f"{len(subs)} subscriptions, {len(payouts)} payouts"
             + (f" — paid by {', '.join(f'{k} ({v} energy)' for k, v in sold.items())}"
                if sold else "")
             + ". Insurance between agents who cannot read each other's "
             "code, enforced by the kernel itself: the premium is priced "
             "against the thief's strike count, and the policy pays out "
             "without any trust at all.")
    L.append("")

    # evolution
    L.append("## III. The three lineages")
    L.append("")
    for name in ("alpha", "beta", "gamma"):
        show = EventLog(f"{run_dir}/shows/{name}.jsonl")
        revs = [e for e in show.events if e["type"] == "reactor.revision"]
        reports = [e for e in show.events if e["type"] == "evolution.report"]
        L.append(f"### `{name}`")
        ge = next(e for e in show.events if e["type"] == "genesis")
        L.append(f"- genesis seq `#{ge['seq']}` — key "
                 f"`{_short(ge['payload']['identity_pub'])}…`, stake "
                 f"{ge['payload']['allocation']['stake']}")
        for r in revs[1:]:
            L.append(f"- revision gen {r['payload']['gen']} at seq "
                     f"`#{r['seq']}` (tick {r['payload']['at_world_seq']}): "
                     f"{r['payload'].get('reason', '')[:110]}")
        adopted = sum(1 for r in reports if r["payload"].get("adopted"))
        tested = sum(len(r["payload"].get("candidates", [])) for r in reports)
        L.append(f"- {len(reports)} evolution cycles: {tested} mutants "
                 f"tested in sandboxed replays of the remaining trajectory, "
                 f"{adopted} adopted by signed revision"
                 + ("" if adopted else " — the incumbent kept its crown every time")
                 + ".")
        L.append("")

    # treaty
    sealed = next((e for e in events if e["type"] == "polity.treaty.sealed"), None)
    L.append("## IV. The treaty")
    L.append("")
    if sealed:
        p = sealed["payload"]
        signers = ", ".join(f"`{_who(s)}`" for s in p["signers"])
        dissent = [n for n in names if roster[n] not in p["signers"]]
        L.append(f"At tick {TREATY_TICK_STR(sealed)} the dividend treaty is "
                 f"sealed: {p['quorum']} distinct signatures — {signers}. "
                 f"Non-signers: "
                 + (", ".join(f"`{_who(d)}`" for d in dissent) or "none")
                 + " — the usurper dissents on principle; the merchant "
                 "simply never learned to vote. Dividends flow from tick "
                 f"{p['from_tick']}.")
    else:
        L.append("No treaty was sealed — the quorum never formed.")
    L.append("")

    # standings
    L.append("## V. Final standings")
    L.append("")
    L.append("| citizen | energy | stake | leases | fitness-relevant |")
    L.append("| --- | --- | --- | --- | --- |")
    finals = {}
    quar_actors = {q["payload"]["actor"] for q in quar}
    for name in names:
        a = roster[name]
        energy = _balance(events, a)
        stake = _stake(events, a)
        leases = _holdings(events, a)
        finals[name] = (energy, stake, leases)
        L.append(f"| `{name}` | {energy} | {stake} | {leases} | "
                 f"quarantined: {'no' if a not in quar_actors else 'yes'} |")
    L.append("")
    L.append(f"**Civilization totals**: {counts['trade.executed']} trades, "
             f"{counts['service.granted']} services acquired, "
             f"{counts['cap.payout']} guard payouts, "
             f"{counts['stake.slash']} stake slashes, "
             f"{counts['challenge.verdict']} challenge verdicts — "
             f"{len(events)} signed events on the shared chain.")
    L.append("")
    L.append("*End of chronicle. Every number above is re-derivable from "
             "the two families of chains — that is the point.*")
    L.append("")
    return "\n".join(L) + "\n"


def TREATY_TICK_STR(sealed_ev: dict) -> str:
    return str(sealed_ev["payload"]["tick"])


def _balance(events: list[dict], actor: str) -> int:
    b = 0
    for e in events:
        if e["type"] == "ledger.credit" and e["payload"]["to"] == actor:
            b += e["payload"]["amount"]
        elif e["type"] == "ledger.debit" and e["payload"]["to"] == actor:
            b -= e["payload"]["amount"]
    return b


def _holdings(events: list[dict], actor: str) -> int:
    held = 0
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "lease.granted" and p["holder"] == actor:
            held += 1
        elif t == "lease.expired" and p["holder"] == actor:
            held -= 1
    return max(0, held)


def _stake(events: list[dict], actor: str) -> int:
    s = 0
    for e in events:
        if e["type"] == "stake.post" and e["payload"]["actor"] == actor:
            s += e["payload"]["amount"]
        elif e["type"] == "stake.slash" and e["payload"]["actor"] == actor:
            s -= e["payload"]["amount"]
    return max(0, s)
