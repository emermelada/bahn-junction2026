"""Score tags by what the board pays: margin counts only on weeks at >= 90% on time.

usage: python lab/frank/gated.py TAG [TAG ...]   (paired on the seeds all tags share)
"""
import glob
import json
import os
import statistics
import sys


def load(tag):
    out = {}
    for p in glob.glob(os.path.join("data", "runs", tag, "*", "summary.json")):
        s = json.load(open(p))
        out[s["seed"]] = s["score"]
    return out


runs = {t: load(t) for t in sys.argv[1:]}
common = set.intersection(*(set(r) for r in runs.values())) if runs else set()
print(f"{'tag':20s} n  ranked  min_ot   mean   gated  p10gated  worst_ot_seeds")
for t, r in runs.items():
    rs = [r[s] for s in sorted(common)]
    m = [x["marginCents"] / 100 for x in rs]
    g = sorted(x["marginCents"] / 100 if x["ranked"] else 0 for x in rs)
    ot = sorted((x["onTimeShare"], s) for s, x in zip(sorted(common), rs))
    print(f"{t:20s} {len(rs):2d} {sum(x['ranked'] for x in rs):3d}/{len(rs):<3d} {ot[0][0]:.3f} {statistics.mean(m):7.0f} {statistics.mean(g):7.0f} {g[len(g)//10]:8.0f}  "
          + " ".join(f"{s}:{o:.3f}" for o, s in ot[:3]))
