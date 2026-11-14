"""Tables from out/scarce_check.csv (scarce_check.py): fire rates on bad vs normal weeks by family and day; the LEAD seeds."""
import csv, collections
ROOT = "C:/Users/franc/Desktop/studia/ElysasSecret/Junction/BahnSpread/v5-quote/research/re/v5"
rows = list(csv.DictReader(open(f"{ROOT}/out/scarce_check.csv", encoding="utf-8")))
DAYS = {2: "Tue24", 3: "Wed", 4: "Thu"}


def fam(r):
    t = r["tag"]
    if any(k in t for k in ("f1", "V1", "V2", "v5", "sc-", "scV")):
        return "fee1"
    if "k-safe" in t or "dcl" in t or t.startswith(("m1", "m2", "int-k", "h2-k", "h2x")):
        return "k-safe"
    return "other"


def when(m):
    if not m:
        return "-"
    m = int(m)
    d = m // 1440
    return f"{['Mon','Tue','Wed','Thu','Fri'][d] if d < 5 else 'Sat'} {m % 1440 // 60:02d}h"


for f in ("k-safe", "fee1", "other"):
    R = [r for r in rows if fam(r) == f and (r["seed"].startswith("fresh") or r["seed"].startswith("dev"))]
    for lab in ("True", "False"):
        S = [r for r in R if r["bad"] == lab]
        if not S:
            continue
        fire = [r for r in S if r["flip"]]
        at24 = [r for r in fire if int(r["flip"]) == 2880]
        wed = [r for r in fire if 2880 < int(r["flip"]) <= 4320]
        late = [r for r in S if r["flip_late"]]
        fee = sum(1 for r in fire if "fee" in r["why"])
        print(f"{f:7s} {'bad' if lab == 'True' else 'normal':6s} n={len(S):4d} fires by Thu00 {len(fire)/len(S):5.1%} (Tue24 {len(at24)/len(S):5.1%}, "
              f"Wed {len(wed)/len(S):5.1%}; by fee {fee}, by warn {len(fire)-fee}) | by Fri24 {len(late)/len(S):5.1%}")
print()
for s in ("fresh-12", "fresh-20", "fresh-07", "fresh-10", "fresh-11", "fresh-14", "fresh-15"):
    R = [r for r in rows if r["seed"] == s]
    n = sum(1 for r in R if r["flip"])
    print(f"{s}: fires in {n}/{len(R)} runs (k-safe {sum(1 for r in R if r['flip'] and fam(r)=='k-safe')}/{sum(1 for r in R if fam(r)=='k-safe')}, "
          f"fee1 {sum(1 for r in R if r['flip'] and fam(r)=='fee1')}/{sum(1 for r in R if fam(r)=='fee1')})")
    for r in R:
        if fam(r) == "fee1" or r["tag"] in ("k-safe-dcl", "h2-k-safe", "k-safe"):
            print(f"   {r['run']:45s} ot={float(r['ontime'] or 0):.3f} bad={r['bad'][0]} Tue24 fee={r['tue24_fee']} warn={r['tue24_warn']} "
                  f"-> {when(r['flip'])} {r['why']} (by Fri: {when(r['flip_late'])})")
