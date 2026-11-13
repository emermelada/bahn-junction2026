"""The acceptance curve: the chance of a yes as a monotone function of a price ratio, learned live from
yes/no outcomes. Used twice: dealers on price over list (a yes falls as the ratio rises), drivers on fee
over typical fee (a yes rises with the ratio).

Observations land on a fixed grid of ratios, split between the two nearest points. Each grid point's
estimate is its observed yes share shrunk towards the caller's prior by `strength` pseudo-observations.
Pool-adjacent-violators then makes the estimates monotone. Old observations fade with a half-life in
world minutes, so the curve follows the week (price war, outage, trust)."""
from __future__ import annotations

import bisect
from typing import Callable, Optional, Sequence


class Curve:
    def __init__(self, grid: Sequence[float], prior: Callable[[float], float], strength: float = 4.0,
                 half_life: Optional[float] = None, decreasing: bool = True):
        if list(grid) != sorted(grid) or len(grid) < 2:
            raise ValueError("grid must hold at least two ratios in rising order")
        self.grid = list(grid)
        self.prior = [min(1.0, max(0.0, prior(r))) for r in self.grid]
        self.strength, self.half_life, self.decreasing = strength, half_life, decreasing
        self.yes = [0.0] * len(self.grid)
        self.n = [0.0] * len(self.grid)
        self.at: Optional[float] = None  # the minute the weights are decayed to
        self._fit: Optional[list[float]] = None

    def observe(self, ratio: float, yes: bool, at: float) -> None:
        self._decay(at)
        weight = self._fade(at)
        i, w = self._locate(ratio)
        for j, share in ((i, 1 - w), (i + 1, w)):
            if share > 0:
                self.n[j] += weight * share
                self.yes[j] += weight * share * yes
        self._fit = None

    def p(self, ratio: float, now: Optional[float] = None) -> float:
        """The chance of a yes at this ratio. Outside the grid, the nearest end."""
        if now is not None:
            self._decay(now)
        fit = self._fit if self._fit is not None else self._refit()
        i, w = self._locate(ratio)
        return fit[i] * (1 - w) + fit[i + 1] * w

    def samples(self, ratio: Optional[float] = None) -> float:
        """Faded observation weight in total, or at the two grid points around a ratio."""
        if ratio is None:
            return sum(self.n)
        i, w = self._locate(ratio)
        return self.n[i] * (1 - w) + self.n[i + 1] * w

    def _fade(self, at: float) -> float:
        """The weight of an observation made at `at`, seen from the current minute."""
        if not self.half_life or self.at is None or at >= self.at:
            return 1.0
        return 0.5 ** ((self.at - at) / self.half_life)

    def _decay(self, now: float) -> None:
        if self.at is not None and now <= self.at:
            return
        if self.half_life and self.at is not None:
            factor = 0.5 ** ((now - self.at) / self.half_life)
            self.yes = [y * factor for y in self.yes]
            self.n = [n * factor for n in self.n]
            self._fit = None
        self.at = now

    def _locate(self, ratio: float) -> tuple[int, float]:
        """The grid interval holding the ratio, and how far along it the ratio sits (0 to 1)."""
        g = self.grid
        if ratio <= g[0]:
            return 0, 0.0
        if ratio >= g[-1]:
            return len(g) - 2, 1.0
        i = bisect.bisect_right(g, ratio) - 1
        return i, (ratio - g[i]) / (g[i + 1] - g[i])

    def _refit(self) -> list[float]:
        s = self.strength
        means = [(y + s * p) / (n + s) for y, n, p in zip(self.yes, self.n, self.prior)]
        weights = [n + s for n in self.n]
        if self.decreasing:
            self._fit = pav(means[::-1], weights[::-1])[::-1]
        else:
            self._fit = pav(means, weights)
        return self._fit


def pav(values: Sequence[float], weights: Sequence[float]) -> list[float]:
    """Weighted pool-adjacent-violators: the closest rising sequence to `values`."""
    blocks: list[list[float]] = []  # [mean, weight, length]
    for v, w in zip(values, weights):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks[-1]
            blocks[-1] = [(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2]
    return [mean for mean, _, length in blocks for _ in range(int(length))]
