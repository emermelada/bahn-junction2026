"""Paired table of run folders from any worktree: python lab/build/pair.py DIR_A DIR_B [DIR_C ...] (each data/runs/<tag>)."""
import glob, json, os, statistics, sys
runs = []
for d in sys.argv[1:]:
    r = {}
    for p in glob.glob(os.path.join(d, "*", "summary.json")):
        s = json.load(open(p))
        r[s["seed"]] = s["score"]
    runs.append(r)
common = sorted(set.intersection(*(set(r) for r in runs)))
names = [os.path.basename(os.path.normpath(d))[:18] for d in sys.argv[1:]]
print(f"paired on {len(common)} seeds")
for n, r in zip(names, runs):
    m = [r[s]["marginCents"] / 100 for s in common]
    ot = [r[s]["onTimeShare"] for s in common]
    rk = sum(r[s]["ranked"] for s in common)
    if m:
        print(f"{n:18s} mean {statistics.mean(m):9.0f} ranked {rk}/{len(common)} min_ot {min(ot):.3f} worst {min(m):8.0f}")
print("seed    " + "".join(f"{n:>20s}" for n in names))
for s in common:
    print(f"{s:8s}" + "".join(f"{r[s]['marginCents']/100:12.0f}/{r[s]['onTimeShare']:.3f}" for r in runs))
if len(runs) >= 2 and common:
    d = [runs[1][s]["marginCents"] / 100 - runs[0][s]["marginCents"] / 100 for s in common]
    se = statistics.stdev(d) / len(d) ** 0.5 if len(d) > 1 else 0
    print(f"{names[1]} - {names[0]}: {statistics.mean(d):+.0f} (se {se:.0f}), up on {sum(x > 0 for x in d)}/{len(d)}")
