"""Seeded randomness. Every random draw in a decision comes from here, so a seed replays exactly."""
from __future__ import annotations

import hashlib
import random


def rng(*parts: object) -> random.Random:
    """A generator seeded by its parts, e.g. rng(world_seed, request_id). Stable across runs and machines."""
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))
