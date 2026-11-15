"""molt-polis — The Living Commonwealth.

The fourth molt challenge. Sovereign Agent Zero proved the self, the
Byzantium Swarm proved the network, the Capability Bazaar proved the
market. The polis composes all three: six citizens — three of them
sovereign, each with its own Ed25519 identity, its own private molt-show
chain, and its own evolving molt-reactor genome — share one deterministic
adversarial economy. Citizens sell and buy capabilities from each other
(guard contracts enforced by the world kernel itself), post stakes that
are slashed on protocol violations, and seal a quorum treaty at the end.
A molt-census cross-audits every citizen's private chain against the
shared polity ledger: mirror fidelity, genome provenance, and bit-exact
deterministic replay of every emission.

Primitive layer (event store, identity, reactor engine) is
Projects/sovereign-agent-zero (the molt-core/molth-show conventions);
the mesh and forge layers established the signed-envelope and
proof-before-trust conventions this polis inherits.
"""
import sys
from pathlib import Path

_SOVEREIGN = Path(__file__).resolve().parents[2] / "sovereign-agent-zero"
if str(_SOVEREIGN) not in sys.path:
    sys.path.insert(0, str(_SOVEREIGN))