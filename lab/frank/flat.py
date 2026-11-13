"""Flat-fee booking success from the decision log: first post ('won') ratio -> warned/expired or not."""
import collections, gzip, json, sys, re
for run in sys.argv[1:]:
    d = json.load(gzip.open(run + "/reveal.json.gz", "rt"))
    reqs = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    first, bad = {}, set()
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        oid = rest.split()[0]
        if code == "POST" and " won " in rest and oid not in first:
            m = re.search(r"legs=\[([\d, ]+)\].*fee0=(\d+)", rest)
            nl = len(m.group(1).split(","))
            q = reqs[oid]
            first[oid] = (int(m.group(2)) / (q["referenceFeeCents"] * nl / len(q["legs"])), int(t), q)
        if code in ("DEADLINE_CLOSE",) or (code == "POST" and " expired " in rest):
            bad.add(oid)
    by = collections.defaultdict(lambda: [0, 0])
    for oid, (f, t, q) in first.items():
        k = round(f, 1)
        by[k][1] += 1
        by[k][0] += oid not in bad
    print(run, {k: f"{v[0]/v[1]:.2f} ({v[1]})" for k, v in sorted(by.items())})
