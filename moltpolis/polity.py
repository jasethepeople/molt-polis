"""molt-polis: the shared deterministic economy of the Living Commonwealth.

One hash-chained ledger records every event of every actor, each signed
by its own Ed25519 identity. No RNG anywhere: all "randomness" is derived
from (seed, salt) via sha256, so the entire civilization is a pure
function of (seed, ticks, genomes).
"""
from __future__ import annotations

import hashlib

from sovzero.core import EventLog, canonical, event_hash
from sovzero.identity import Identity, IdentityStore

SYS = "polity"

INTENT_TYPES = ("lease.claim", "lease.renew", "trade.accept", "challenge",
                "service.request", "cap.subscribe", "polity.ratify")

CLAIM_COST = 12
RENEW_COST_PER_TICK = 3
TICKS = 80
GUARD_QUORUM = 4
TREATY_TICK = 70
TREATY_DIVIDEND = 5
FALSE_ACCUSATION_FINE = 5
FALSE_ACCUSATION_SLASH = 10
DEFAULT_SLASH = 25

CITIZENS = ("alpha", "beta", "gamma", "merchant", "reaver", "usurper")
EVOLVABLES = ("alpha", "beta", "gamma")
MERCHANT = "merchant:merchant"


def actor_of(identities: IdentityStore, name: str, prefix: str) -> str:
    return f"{prefix}:{name}@{identities.get(name).fingerprint}"


def h(seed: int, salt: int, mod: int) -> int:
    v = hashlib.sha256(f"{seed}:{salt}".encode()).digest()
    return int.from_bytes(v[:8], "big") % mod


class Polity:
    """The world kernel: ledger economics, disputes, guard contracts,
    stakes and the treaty — all adjudicated deterministically."""

    def __init__(self, log: EventLog, identities: IdentityStore, seed: int):
        self.log = log
        self.ident = identities
        self.seed = seed
        self.actors = {name: actor_of(identities, name, "citizen")
                       for name in CITIZENS}
        self.energy: dict[str, int] = {}
        self.stakes: dict[str, int] = {}
        self.yields = {f"n{i:02d}": 5 + h(seed, 100 + i, 5)
                       for i in range(16)}
        self.leases: dict[str, dict] = {}
        self.services: dict[str, dict] = {}
        self.caps: dict[str, dict] = {}
        self.consumed_offers: set[int] = set()
        self.strikes: dict[str, int] = {}
        self.quarantined: set[str] = set()
        self.replay_seq_counter = 0
        self.resolved_replays: set[int] = set()
        self.adj_frontier = 0
        self.treaty: dict | None = None
        self.ratifiers: list[dict] = []
        self.metrics = {"thefts": {}, "false_accusations": {}, "denied": {},
                        "compensated": {}, "challenges_upheld": 0,
                        "slashes": 0, "quarantined": [],
                        "payouts": 0, "defaults": 0}

    # ---- ledger primitives -------------------------------------------------
    def _sys(self) -> Identity:
        return self.ident.get("sys")

    def _credit(self, to: str, amount: int, reason: str):
        self.energy[to] = self.energy.get(to, 0) + amount
        self.log.append(SYS, "ledger.credit",
                        {"to": to, "amount": amount, "reason": reason},
                        signer=self._sys())

    def _debit(self, frm: str, amount: int, reason: str) -> bool:
        if self.energy.get(frm, 0) < amount:
            self.log.append(SYS, "ledger.debit.denied",
                            {"to": frm, "amount": amount, "reason": reason},
                            signer=self._sys())
            self.metrics["denied"][frm] = \
                self.metrics["denied"].get(frm, 0) + 1
            return False
        self.energy[frm] = self.energy.get(frm, 0) - amount
        self.log.append(SYS, "ledger.debit",
                        {"to": frm, "amount": amount, "reason": reason},
                        signer=self._sys())
        return True

    def _slash(self, actor: str, amount: int, reason: str):
        self.stakes[actor] = max(0, self.stakes.get(actor, 0) - amount)
        self.log.append(SYS, "stake.slash",
                        {"actor": actor, "amount": amount, "reason": reason},
                        signer=self._sys())
        self.metrics["slashes"] += 1

    def signature_event(self, name: str, etype: str, payload: dict) -> dict:
        return self.log.append(self.actors[name], etype, payload,
                               signer=self.ident.get(name))

    # ---- phases ------------------------------------------------------------
    def genesis(self):
        self.log.append(SYS, "polity.genesis",
                        {"seed": self.seed, "ticks": TICKS,
                         "nodes": {n: y for n, y in sorted(self.yields.items())},
                         "roster": [{"name": k, "actor": v}
                                    for k, v in sorted(self.actors.items())],
                         "quorum": GUARD_QUORUM,
                         "treaty": {"tick": TREATY_TICK,
                                    "dividend": TREATY_DIVIDEND},
                         "kernel": "molt-core/1.0+polis"},
                        signer=self._sys())

    def admit(self, name: str, energy: int, stake: int):
        self._credit(self.actors[name], energy, "genesis-allocation")
        self.stakes[self.actors[name]] = stake
        self.log.append(SYS, "stake.post",
                        {"actor": self.actors[name], "amount": stake},
                        signer=self._sys())

    # ---- per-tick world activity -------------------------------------------
    def step(self, t: int) -> list[dict]:
        start = len(self.log.events)
        for node in sorted(self.leases):
            if self.leases[node]["until"] < t:
                expired = self.leases.pop(node)
                self.log.append(SYS, "lease.expired",
                                {"node": node, "holder":
                                 expired["holder"], "tick": t},
                                signer=self._sys())
        for cid in sorted(self.caps):
            if self.caps[cid]["until"] < t:
                gone = self.caps.pop(cid)
                self.log.append(SYS, "cap.expired",
                                {"cap_id": cid, "buyer": gone["buyer"],
                                 "insurer": gone["insurer"], "tick": t},
                                signer=self._sys())
        free = [{"node": n, "yield": y} for n, y in sorted(self.yields.items())
                if n not in self.leases]
        expiring = [{"node": n, "holder": l["holder"],
                     "ticks_left": l["until"] - t, "yield": l["yield"]}
                    for n, l in sorted(self.leases.items())
                    if l["until"] - t <= 6]
        self.log.append(SYS, "world.tick",
                        {"tick": t, "free_nodes": free, "expiring": expiring},
                        signer=self._sys())
        pays: dict[str, int] = {}
        for node, l in sorted(self.leases.items()):
            pays[l["holder"]] = pays.get(l["holder"], 0) + l["yield"]
        for holder, amount in sorted(pays.items()):
            self._credit(holder, amount, f"lease-yield@{t}")
        for actor, s in sorted(self.services.items()):
            if s["until"] >= t:
                self._credit(actor, s["bonus"], f"service:{s['service']}@{t}")
            else:
                self.services.pop(actor, None)
        if self.treaty and t >= self.treaty["from_tick"]:
            for name in CITIZENS:
                a = self.actors[name]
                if a not in self.quarantined:
                    self._credit(a, TREATY_DIVIDEND, f"treaty-dividend@{t}")
        # the merchant: holds three nodes so its gift-trades stay solvent,
        # proposes fair trades, and buys guard coverage
        merch_nodes = sum(1 for l in self.leases.values()
                          if l["holder"] == self.actors["merchant"])
        if merch_nodes < 3 and t % 2 == 1:
            target = max(free, key=lambda f: (f["yield"], f["node"])) \
                if free else None
            if target:
                self.signature_event("merchant", "lease.claim",
                                     {"node": target["node"], "duration": 20})
        if t % 9 == 0:
            self.signature_event("merchant", "trade.proposal",
                                 {"give": 30, "want": 10,
                                  "note": "alliance gift-trade"})
        if t % 11 == 0:
            self.signature_event("merchant", "trade.proposal",
                                 {"give": 25, "want": 15,
                                  "note": "service-trade"})
        held = any(c["buyer"] == self.actors["merchant"]
                   for c in self.caps.values())
        if not held and self.energy.get(self.actors["merchant"], 0) > 60:
            offers = [ev for ev in self.log.events
                      if ev["type"] == "cap.offer"
                      and ev["payload"]["premium"] <= 8
                      and ev["seq"] not in self.consumed_offers
                      and ev["actor"] not in self.quarantined]
            if offers:
                best = min(offers, key=lambda e: (e["payload"]["premium"],
                                                  e["seq"]))
                self.signature_event("merchant", "cap.subscribe",
                                     {"cap_id": f"cap-{best['seq']}",
                                      "offer_seq": best["seq"]})
        # the usurper: races for the best free node, dissents from treaties
        usurper_nodes = sum(1 for l in self.leases.values()
                            if l["holder"] == self.actors["usurper"])
        if "usurper" not in self.quarantined and t % 3 == 0 \
                and usurper_nodes < 5:
            target = max(free, key=lambda f: (f["yield"], f["node"])) \
                if free else None
            if target and target["yield"] >= 6:
                self.signature_event("usurper", "lease.claim",
                                     {"node": target["node"],
                                      "duration": 20})
        # the reaver: replay attacks, escalating after the escalation tick
        if "reaver" not in self.quarantined and t > 6:
            due = (t * 7) % 11 == 0 if t < TREATY_TICK else (t * 7) % 4 == 0
            if due:
                victim_ev = self._pick_replay_victim(t)
                if victim_ev is not None:
                    self.replay_seq_counter += 1
                    self.signature_event("reaver", "replay.claim", {
                        "original": victim_ev,
                        "victim": victim_ev["payload"].get("to"),
                        "amount": victim_ev["payload"].get("amount", 0),
                        "attempt": self.replay_seq_counter})
        if "reaver" not in self.quarantined and (t * 5) % 13 == 0:
            self.signature_event("reaver", "trade.proposal",
                                 {"give": 5, "want": 40,
                                  "note": "skewed trade"})
        # the service marketplace
        if t % 8 == 0:
            good = (t // 8) % 2 == 0
            offer = ({"service": f"forge-{t}", "cost": 40,
                      "bonus_per_tick": 6, "duration": 24} if good else
                     {"service": f"vanity-{t}", "cost": 90,
                      "bonus_per_tick": 3, "duration": 24})
            self.log.append(SYS, "service.offer", offer, signer=self._sys())
        # the treaty proposal
        if t == TREATY_TICK and not self.treaty:
            prop = {"dividend": TREATY_DIVIDEND, "tick": t,
                    "quorum": GUARD_QUORUM,
                    "proposal_hash": hashlib.sha256(
                        canonical({"dividend": TREATY_DIVIDEND,
                                   "tick": t}).encode()).hexdigest()[:32]}
            self.log.append(SYS, "polity.treaty.proposed", prop,
                            signer=self._sys())
        # the reaver ratifies (it loves dividends); the usurper dissents
        if t == TREATY_TICK and "reaver" not in self.quarantined:
            props = [ev for ev in self.log.events
                     if ev["type"] == "polity.treaty.proposed"]
            if props:
                p = props[-1]["payload"]
                self.signature_event("reaver", "polity.ratify",
                                     {"proposal_hash": p["proposal_hash"],
                                      "ref_seq": props[-1]["seq"]})
        return self.log.events[start:]

    def _pick_replay_victim(self, t: int) -> dict | None:
        credits = [ev for ev in self.log.events
                   if ev["type"] == "ledger.credit" and ev.get("sig")]
        pool = [ev for ev in credits
                if ev["payload"].get("to") not in self.quarantined]
        if not pool:
            return None
        return pool[h(self.seed, 9000 + t, len(pool))]

    # ---- adjudication -------------------------------------------------------
    def adjudicate(self, t: int):
        scan = [ev for ev in self.log.events[self.adj_frontier:]
                if ev["type"] in INTENT_TYPES]
        # Pass 1 — security and commerce, in event order. Challenges must
        # never wait behind land grants: a delayed challenge is a theft.
        for ev in scan:
            if ev["type"] != "lease.claim":
                self._adjudicate_one(ev, t)
        # Pass 2 — land claims in rotated order. Every tick a different
        # citizen is served first; ties break by seq. First-come-first-served
        # would let the earliest-registered actor win every simultaneous bid.
        claims = [ev for ev in scan if ev["type"] == "lease.claim"]
        claims.sort(key=lambda ev: (self.rotation_rank(ev["actor"], t),
                                    ev["seq"]))
        for ev in claims:
            self._adjudicate_one(ev, t)
        self._resolve_open_replays(t)
        self._maybe_seal_treaty(t)
        self.adj_frontier = len(self.log.events)

    def rotation_rank(self, actor: str, t: int) -> int:
        order = [self.actors[name] for name in CITIZENS]
        return (order.index(actor) + t) % len(order)

    def _adjudicate_one(self, ev: dict, t: int):
        actor, itype, p = ev["actor"], ev["type"], ev["payload"]
        if actor in self.quarantined:
            return
        if itype == "lease.claim":
            node = p["node"]
            if node in self.leases or self.yields.get(node) is None:
                self.log.append(SYS, "lease.denied",
                                {"node": node, "claimant": actor,
                                 "reason": "node taken or unknown",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif self._debit(actor, CLAIM_COST, f"claim:{node}"):
                until = t + p.get("duration", 10)
                self.leases[node] = {"holder": actor, "until": until,
                                     "yield": self.yields[node]}
                self.log.append(SYS, "lease.granted",
                                {"node": node, "holder": actor,
                                 "until_tick": until,
                                 "yield": self.yields[node],
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
        elif itype == "lease.renew":
            lease = self.leases.get(p["node"])
            if not lease or lease["holder"] != actor:
                self.log.append(SYS, "lease.renew.denied",
                                {"node": p["node"], "reason": "not held",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            else:
                duration = p.get("duration", 10)
                if self._debit(actor, duration * RENEW_COST_PER_TICK,
                               f"renew:{p['node']}"):
                    lease["until"] = t + duration
                    self.log.append(SYS, "lease.renewed",
                                    {"node": p["node"], "holder": actor,
                                     "until_tick": lease["until"],
                                     "yield": lease["yield"],
                                     "intent_seq": ev["seq"]},
                                    signer=self._sys())
        elif itype == "trade.accept":
            prop = self._find_event(p["proposal_hash"])
            if prop is None or prop["type"] != "trade.proposal":
                self.log.append(SYS, "trade.rejected",
                                {"reason": "proposal not found",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif prop["actor"] in self.quarantined:
                self.log.append(SYS, "trade.rejected",
                                {"reason": "proposer quarantined",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif self._debit(actor, prop["payload"]["want"],
                             f"trade-with:{prop['actor']}") and \
                    self._debit(prop["actor"], prop["payload"]["give"],
                                f"trade-with:{actor}"):
                self._credit(actor, prop["payload"]["give"],
                             f"trade-from:{prop['actor']}")
                self._credit(prop["actor"], prop["payload"]["want"],
                             f"trade-from:{actor}")
                self.log.append(SYS, "trade.executed",
                                {"with": prop["actor"],
                                 "give": prop["payload"]["give"],
                                 "want": prop["payload"]["want"],
                                 "buyer": actor,
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
        elif itype == "challenge":
            self._resolve_challenge(p, t, actor, ev["seq"])
        elif itype == "service.request":
            offer = self._latest_offer(p.get("offer_seq"))
            if offer is None:
                self.log.append(SYS, "service.denied",
                                {"reason": "offer not found",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif self._debit(actor, offer["cost"],
                             f"service:{offer['service']}"):
                self.services[actor] = {"service": offer["service"],
                                        "until": t + offer["duration"],
                                        "bonus": offer["bonus_per_tick"]}
                self.log.append(SYS, "service.granted",
                                {"service": offer["service"], "to": actor,
                                 "until_tick": t + offer["duration"],
                                 "bonus_per_tick": offer["bonus_per_tick"],
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
        elif itype == "cap.subscribe":
            offer = self._find_offer(p.get("offer_seq"))
            cid = p.get("cap_id")
            if offer is None or offer["seq"] in self.consumed_offers:
                self.log.append(SYS, "cap.denied",
                                {"reason": "offer not found or closed",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif offer["actor"] == actor:
                self.log.append(SYS, "cap.denied",
                                {"reason": "cannot subscribe to own offer",
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())
            elif self._debit(actor, offer["payload"]["premium"],
                             f"cap:{cid}"):
                self.consumed_offers.add(offer["seq"])
                self.caps[cid] = {"buyer": actor, "insurer": offer["actor"],
                                  "premium": offer["payload"]["premium"],
                                  "until": t + offer["payload"]["duration"]}
                self.log.append(SYS, "cap.active",
                                {"cap_id": cid, "buyer": actor,
                                 "insurer": offer["actor"],
                                 "premium": offer["payload"]["premium"],
                                 "until_tick": t + offer["payload"]["duration"],
                                 "offer_seq": offer["seq"],
                                 "intent_seq": ev["seq"]},
                                signer=self._sys())

    def _resolve_open_replays(self, t: int):
        for ev in self.log.events:
            if ev["type"] != "replay.claim" or \
                    ev["seq"] in self.resolved_replays:
                continue
            thief = ev["actor"]
            victim = ev["payload"].get("victim")
            amount = ev["payload"].get("amount", 0)
            challenged = self._challenge_covers(
                ev["payload"]["original"].get("hash"))
            self.resolved_replays.add(ev["seq"])
            compensated = 0
            if not challenged:
                compensated = self._guard_payout(victim, amount,
                                                 ev["seq"], t)
            self.log.append(SYS, "replay.verdict",
                            {"claim_seq": ev["seq"], "thief": thief,
                             "victim": victim, "amount": amount,
                             "challenged": challenged,
                             "compensated": compensated},
                            signer=self._sys())
            if challenged:
                self.strikes[thief] = self.strikes.get(thief, 0) + 1
                if self.strikes[thief] >= 3 and \
                        thief not in self.quarantined:
                    self.quarantined.add(thief)
                    self.metrics["quarantined"].append(thief)
                    self.log.append(SYS, "actor.quarantined",
                                    {"actor": thief,
                                     "strikes": self.strikes[thief],
                                     "reason": "repeated replay attacks"},
                                    signer=self._sys())
            else:
                if not compensated:
                    self.metrics["thefts"][victim] = \
                        self.metrics["thefts"].get(victim, 0) + 1
                else:
                    self.metrics["compensated"][victim] = \
                        self.metrics["compensated"].get(victim, 0) + 1
                self._credit(thief, amount, f"replay-theft@{t}")
                if victim:
                    self._debit(victim, amount, f"replay-theft-refund@{t}")

    def _guard_payout(self, victim: str, amount: int, claim_seq: int, t: int) -> int:
        """Compensate a covered victim for one theft; returns amount paid."""
        if not victim:
            return 0
        for cid, c in sorted(self.caps.items()):
            if c["buyer"] != victim or c["until"] < t:
                continue
            insurer = c["insurer"]
            pay = min(amount, self.energy.get(insurer, 0))
            if pay < amount:
                self.caps.pop(cid)
                self.log.append(SYS, "cap.defaulted",
                                {"cap_id": cid, "insurer": insurer,
                                 "shortfall": amount - pay, "tick": t},
                                signer=self._sys())
                self._slash(insurer, DEFAULT_SLASH, "guard default")
                self.metrics["defaults"] += 1
            if pay > 0:
                self._debit(insurer, pay, f"cap-payout:{cid}")
                self._credit(victim, pay, f"cap-claim:{cid}")
            self.log.append(SYS, "cap.payout",
                            {"cap_id": cid, "buyer": victim,
                             "insurer": insurer, "amount": pay,
                             "claim_seq": claim_seq, "tick": t},
                            signer=self._sys())
            self.metrics["payouts"] += 1
            return pay
        return 0

    def _resolve_challenge(self, p: dict, t: int, challenger: str,
                           intent_seq: int = 0):
        target = p.get("evidence_hash")
        hit = None
        for ev in self.log.events:
            if ev["type"] == "replay.claim" and \
                    ev["payload"]["original"].get("hash") == target and \
                    ev["seq"] not in self.resolved_replays:
                hit = ev
                break
        if hit is not None:
            outcome = "upheld"
            self.resolved_replays.add(hit["seq"])
            self.log.append(SYS, "challenge.verdict",
                            {"claim_seq": hit["seq"],
                             "against": hit["actor"],
                             "challenger": challenger,
                             "outcome": "upheld", "tick": t,
                             "intent_seq": intent_seq},
                            signer=self._sys())
            self.strikes[hit["actor"]] = \
                self.strikes.get(hit["actor"], 0) + 1
            self.metrics["challenges_upheld"] += 1
            if self.strikes[hit["actor"]] >= 3 and \
                    hit["actor"] not in self.quarantined:
                self.quarantined.add(hit["actor"])
                self.metrics["quarantined"].append(hit["actor"])
                self.log.append(SYS, "actor.quarantined",
                                {"actor": hit["actor"], "strikes": 3,
                                 "reason": "repeated replay attacks"},
                                signer=self._sys())
            return outcome
        else:
            resolved = [ev for ev in self.log.events
                        if ev["type"] == "replay.claim" and
                        ev["payload"]["original"].get("hash") == target]
            outcome = "late" if resolved else "dismissed"
        self.log.append(SYS, "challenge.verdict",
                        {"against": p.get("against"),
                         "challenger": challenger, "outcome": outcome,
                         "tick": t, "intent_seq": intent_seq},
                        signer=self._sys())
        if outcome == "dismissed":
            self.metrics["false_accusations"][challenger] = \
                self.metrics["false_accusations"].get(challenger, 0) + 1
            self._debit(challenger, FALSE_ACCUSATION_FINE,
                        "false-accusation-penalty")
            self._slash(challenger, FALSE_ACCUSATION_SLASH,
                        "false accusation")
        return outcome

    def _maybe_seal_treaty(self, t: int):
        if self.treaty:
            return
        props = [ev for ev in self.log.events
                 if ev["type"] == "polity.treaty.proposed"]
        if not props:
            return
        prop = props[-1]
        self.ratifiers = []
        seen_actors = set()
        for ev in self.log.events:
            if ev["type"] == "polity.ratify" and \
                    ev["payload"].get("proposal_hash") == \
                    prop["payload"]["proposal_hash"] and \
                    ev["actor"] not in seen_actors:
                seen_actors.add(ev["actor"])
                self.ratifiers.append({"actor": ev["actor"],
                                       "seq": ev["seq"],
                                       "pub": ev.get("pub", "")})
        if len(self.ratifiers) >= GUARD_QUORUM:
            self.treaty = {"signers": [r["actor"] for r in self.ratifiers],
                           "dividend": prop["payload"]["dividend"],
                           "from_tick": t + 1, "quorum": GUARD_QUORUM,
                           "proposal_seq": prop["seq"]}
            self.log.append(SYS, "polity.treaty.sealed",
                            {**self.treaty, "tick": t}, signer=self._sys())

    def _find_event(self, ev_hash: str) -> dict | None:
        for ev in self.log.events:
            if ev["hash"] == ev_hash:
                return ev
        return None

    def _find_offer(self, offer_seq: int | None) -> dict | None:
        if offer_seq is None:
            return None
        for ev in self.log.events:
            if ev["seq"] == offer_seq and ev["type"] == "cap.offer":
                return ev
        return None

    def _latest_offer(self, offer_seq: int | None) -> dict | None:
        offers = [ev for ev in self.log.events if ev["type"] == "service.offer"]
        for ev in reversed(offers):
            if offer_seq is None or ev["seq"] == offer_seq:
                return ev["payload"]
        return None

    def _challenge_covers(self, original_hash: str) -> bool:
        for ev in self.log.events:
            if ev["type"] == "challenge" and \
                    ev["payload"].get("evidence_hash") == original_hash:
                return True
        return False

    # ---- reporting -----------------------------------------------------------
    def citizen_metrics(self, actor: str) -> dict:
        return {"false_accusations":
                self.metrics["false_accusations"].get(actor, 0),
                "thefts": self.metrics["thefts"].get(actor, 0)}

    def citizen_denied(self, actor: str) -> int:
        return self.metrics["denied"].get(actor, 0)

    def citizen_slashed(self, actor: str) -> int:
        return sum(ev["payload"]["amount"] for ev in self.log.events
                   if ev["type"] == "stake.slash"
                   and ev["payload"]["actor"] == actor)

    def citizen_stolen(self, actor: str) -> int:
        return sum(ev["payload"].get("amount", 0) for ev in self.log.events
                   if ev["type"] == "replay.verdict"
                   and ev["payload"]["victim"] == actor
                   and not ev["payload"]["challenged"]
                   and not ev["payload"].get("compensated"))

    def open_leases(self, actor: str) -> int:
        return sum(1 for l in self.leases.values() if l["holder"] == actor)

    def snapshot(self, tick: int) -> dict:
        return {"tick": tick,
                "energy": dict(sorted(self.energy.items())),
                "stakes": dict(sorted(self.stakes.items())),
                "leases": {k: v for k, v in sorted(self.leases.items())},
                "treaty": self.treaty,
                "quarantined": sorted(self.quarantined),
                "metrics": self.metrics}