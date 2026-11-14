"""Expected fee paid per car / typical fee, at quote time (research/re/market/v4/fee_fit.py).

Fitted on 299,628 won cars of 681 k-safe-family tuning weeks: the car's share of its gigs' fees by typical fee. Held-out seeds
(dev-43..54): R2 0.21 against 0.02 for the week's mean; deciles run from 0.90x (cars that end where drivers live, often paired)
to 1.23x typical (lone cars ending far from drivers' homes, 10% late). Same feature vector as late_gbm.py.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .desk import Desk

_MODEL: dict = {}


def model() -> dict:
    if not _MODEL:
        with open(os.path.join(os.path.dirname(__file__), "fee_gbm.json"), encoding="utf-8") as f:
            _MODEL.update(json.load(f))
    return _MODEL


def score(x: list[float]) -> float:
    m = model()
    z = m["base"]
    for node in m["trees"]:
        while len(node) > 1:
            f, thr, miss_left, left, right = node
            v = x[f]
            node = (left if miss_left else right) if v != v else (left if v <= thr else right)
        z += node[0]
    return z


class FeeModel:
    """Per-car fee shape: the trees' fee for this car over the trees' mean on our recent wins, so the week's fee level stays
    the desk's own cost_mult and only the split between cheap and dear cars changes."""

    def __init__(self, desk: "Desk"):
        from .late_gbm import LateModel
        self.desk = desk
        self.feats = LateModel(desk)
        self.won: list[float] = []  # the trees' fee mult of each car we won, at its quote

    def mult(self, r: dict, opt: dict) -> float:
        f = self.feats.features(r, opt)
        return min(2.0, max(0.5, score([float(f[k]) for k in model()["features"]])))

    def level(self) -> float:
        n = self.desk.cfg.cost_prior_n
        xs = self.won[-150:]
        return (1.0 * n + sum(xs)) / (n + len(xs))  # 1.0: the trees' mean on the training cars (1.003)
