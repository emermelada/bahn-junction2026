"""Pair a tag (data/runs/<tag>) against the team's c3 runs on every seed set (read-only from the other worktrees).
usage: python lab/build/vsc3.py TAG [TAG2 ...]"""
import glob, json, os, statistics, sys
BASES = ["../v1-evening/data/runs/c3-guard92-late12", "../v1-b/data/runs/c3-val", "../v1-a/data/runs/base-c3-war", "data/runs/A-c3", "data/runs/R-c3-repro"]
WAR = {f"dev-{n}" for n in (20, 23, 26, 29, 32, 35, 37, 39, 40, 41, 42)}
def load(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*", "summary.json")):
        try:
            s = json.load(open(p)); out[s["seed"]] = s["score"]
        except Exception:
            pass
    return out
base = {}
for b in BASES:
    base.update(load(b))
for tag in sys.argv[1:]:
    runs = load(os.path.join("data", "runs", tag))
    print(f"== {tag}")
    for name, sel in (("dev-07..18", lambda s: 7 <= int(s[4:]) <= 18), ("dev-43..54", lambda s: 43 <= int(s[4:]) <= 54), ("WAR", lambda s: s in WAR)):
        seeds = sorted(s for s in runs if s in base and sel(s))
        if not seeds:
            continue
        a = [base[s]["marginCents"] / 100 for s in seeds]; b = [runs[s]["marginCents"] / 100 for s in seeds]
        d = [y - x for x, y in zip(a, b)]
        se = statistics.stdev(d) / len(d) ** 0.5 if len(d) > 1 else 0
        rk_a = sum(base[s]["ranked"] for s in seeds); rk_b = sum(runs[s]["ranked"] for s in seeds)
        print(f"  {name:10s} n={len(seeds):2d} c3 {statistics.mean(a):8.0f} ({rk_a}/{len(seeds)} ranked, min {min(base[s]['onTimeShare'] for s in seeds):.3f})"
              f"  arm {statistics.mean(b):8.0f} ({rk_b}/{len(seeds)}, min {min(runs[s]['onTimeShare'] for s in seeds):.3f})  diff {statistics.mean(d):+6.0f} se {se:4.0f} up {sum(x > 0 for x in d)}/{len(d)}")
        print("    " + " ".join(f"{s[4:]}:{dd:+.0f}" for s, dd in zip(seeds, d)))
