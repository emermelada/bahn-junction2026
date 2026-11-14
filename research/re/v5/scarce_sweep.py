"""Threshold sweep of the scarcity rule on out/scarce_series.csv (k-safe + fee1 families, holdouts excluded)."""
import csv, json
ROOT = "C:/Users/franc/Desktop/studia/ElysasSecret/Junction/BahnSpread/v5-quote/research/re/v5"
rows = list(csv.DictReader(open(f"{ROOT}/out/scarce_series.csv", encoding="utf-8")))
for r in rows:
    r["s"] = json.loads(r["series"])
    r["f1"] = any(k in r["tag"] for k in ("f1", "V1", "V2", "v5", "sc-", "scV"))
    r["low"] = float(r["ontime"] or 1) < 0.93


def first(r, ok, upto=24):
    for i, (f, w) in enumerate(r["s"][:upto + 1]):
        if ok(f, w):
            return i
    return None


RULES = {"spec: fee>=1.08 or w>=0.06": lambda f, w: f >= 1.08 or w >= 0.06,
         "fee>=1.08 or w>=0.08": lambda f, w: f >= 1.08 or w >= 0.08,
         "fee>=1.08 or w>=0.10": lambda f, w: f >= 1.08 or w >= 0.10,
         "fee>=1.08 only": lambda f, w: f >= 1.08,
         "fee>=1.05 and w>=0.06": lambda f, w: f >= 1.05 and w >= 0.06,
         "fee>=1.03 and w>=0.06": lambda f, w: f >= 1.03 and w >= 0.06,
         "fee>=1.10 or w>=0.10": lambda f, w: f >= 1.10 or w >= 0.10,
         "w>=0.06 only": lambda f, w: w >= 0.06}
for fam in (False, True):
    R = [r for r in rows if r["f1"] == fam]
    print(f"== {'fee1 family' if fam else 'k-safe family'}: {len(R)} weeks; PROBE-bad {sum(r['bad']=='True' for r in R)}, on-time<0.93 {sum(r['low'] for r in R)}")
    for name, ok in RULES.items():
        out = []
        for lab, sel in (("bad", lambda r: r["bad"] == "True"), ("norm", lambda r: r["bad"] != "True"), ("ot<.93", lambda r: r["low"]), ("ot>=.93", lambda r: not r["low"])):
            S = [r for r in R if sel(r)]
            fl = [first(r, ok) for r in S]
            n = sum(x is not None for x in fl)
            t24 = sum(x == 0 for x in fl)
            out.append(f"{lab} {n/max(1,len(S)):4.0%}({t24/max(1,len(S)):3.0%})")
        print(f"  {name:28s} " + "  ".join(out))
print("\n-- by check window (fee1 family): fires bad / normal / ot<.93 / ot>=.93")
R = [r for r in rows if r["f1"]]
for name, ok in (("spec", RULES["spec: fee>=1.08 or w>=0.06"]), ("fee>=1.10 or w>=0.10", RULES["fee>=1.10 or w>=0.10"]), ("fee>=1.08 only", RULES["fee>=1.08 only"])):
    for upto, lab in ((0, "Tue24 only"), (12, "to Wed12"), (24, "to Thu00")):
        c = [sum(first(r, ok, upto) is not None for r in R if sel(r)) / max(1, sum(1 for r in R if sel(r)))
             for sel in (lambda r: r["bad"] == "True", lambda r: r["bad"] != "True", lambda r: r["low"], lambda r: not r["low"])]
        print(f"  {name:22s} {lab:10s} " + " / ".join(f"{x:4.0%}" for x in c))
