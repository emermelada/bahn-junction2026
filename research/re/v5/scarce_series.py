"""Offline check of the V5 scarcity switch (desk.check_scarcity) on recorded weeks: the exact rule, hour by hour.
Rule: at each hour boundary H from Tue 24:00 (2880) to Thu 00:00 (4320), over events at H-1440 <= at < H: mean booked fee / typical of
single-order gigs (>= 20 bookings) >= 1.08, or distinct warned orders / won orders (>= 20 wins) >= 0.06. Also the first H up to Fri 24:00.
Bad week (PROBE's label, probe/scarcity.py): whole-week booked fee/typ >= 1.10 or warned events / won >= 0.15. Holdouts excluded.
usage: python -I scarce_check.py -> research/re/v5/out/scarce_check.csv"""
import csv, glob, gzip, json, os, re, sys
from multiprocessing import Pool
ROOT = "C:/Users/franc/Desktop/studia/ElysasSecret/Junction/BahnSpread"
HOLD = re.compile(r"^(nf-\d+|dev-(5[5-9]|6[0-6]))-L8$")
FEE, WARN, MIN_N, DAY = 1.08, 0.06, 20, 1440


def rule(book, won, warn, H):
    fees = [x for at, x in book if H - DAY <= at < H]
    w = sum(1 for at in won if H - DAY <= at < H)
    k = len({o for at, o in warn if H - DAY <= at < H})
    fee = sum(fees) / len(fees) if len(fees) >= MIN_N else 0.0
    share = k / w if w >= MIN_N else 0.0
    return fee, share, k, w


def week(path):
    try:
        d = json.load(gzip.open(path, "rt", encoding="utf-8"))
        s = json.load(open(os.path.join(os.path.dirname(path), "summary.json"), encoding="utf-8"))
    except Exception:
        return None
    ev = sorted(d["events"], key=lambda e: e.get("seq", 0))
    req = {r["request"]["id"]: r["request"] for r in d["reveal"]["requests"]}
    gigs = {g["id"]: g for g in d.get("gigs", [])}
    book, allr = [], []
    for e in ev:
        if e["kind"] != "gig_booked" or e["gigId"] not in gigs:
            continue
        st = [x for x in gigs[e["gigId"]]["stops"] if x["kind"] == "pickup"]
        oids = {x["orderId"] for x in st}
        typ = sum(req[x["orderId"]]["referenceFeeCents"] / len(req[x["orderId"]]["legs"]) for x in st if x["orderId"] in req)
        if typ <= 0:
            continue
        allr.append(e["feeCents"] / typ)
        if len(oids) == 1:
            book.append((e["at"], e["feeCents"] / typ))
    won = [e["at"] for e in ev if e["kind"] == "order_won"]
    warn = [(e["at"], e["orderId"]) for e in ev if e["kind"] == "deadline_close"]
    if not won:
        return None
    parts = path.replace("\\", "/").split("/")
    r = dict(run=f"{parts[-6]}/{parts[-3]}/{parts[-2]}", seed=parts[-2][:-3], tag=parts[-3], won=len(won),
             ontime=s.get("score", {}).get("onTimeShare"), margin=s.get("score", {}).get("marginCents", 0) / 100,
             fee_week=sum(allr) / max(1, len(allr)), warn_week=len(warn) / len(won))
    r["bad"] = r["fee_week"] >= 1.10 or r["warn_week"] >= 0.15
    f, sh, k, w = rule(book, won, warn, 2880)
    r.update(tue24_fee=round(f, 3), tue24_warn=f"{k}/{w}", tue24_share=round(sh, 3))
    r["series"] = json.dumps([[round(x, 4) for x in rule(book, won, warn, h * 60)[:2]] for h in range(48, 109)])
    r["flip"], r["why"], r["flip_late"] = None, "", None
    for h in range(48, 109):  # through Fri 24:00 (6480)
        f, sh, k, w = rule(book, won, warn, h * 60)
        if f >= FEE or sh >= WARN:
            if r["flip_late"] is None:
                r["flip_late"] = h * 60
            if h * 60 <= 4320 and r["flip"] is None:
                r["flip"] = h * 60
                r["why"] = ("fee%.3f" % f if f >= FEE else "") + (" warn%d/%d" % (k, w) if sh >= WARN else "")
            break
    return r


if __name__ == "__main__":
    FAM = re.compile(r"(f1|V1|V2|v5|sc-|scV|k-safe|dcl)")
    paths = [p for p in glob.glob(f"{ROOT}/*/data/runs/*/*-L8/reveal.json.gz")
             if not HOLD.match(p.replace("\\", "/").split("/")[-2]) and FAM.search(p.replace("\\", "/").split("/")[-3])]
    print(len(paths), "weeks", flush=True)
    with Pool(8) as pool:
        rows = [r for r in pool.imap_unordered(week, paths, chunksize=4) if r]
    os.makedirs(f"{ROOT}/v5-quote/research/re/v5/out", exist_ok=True)
    with open(f"{ROOT}/v5-quote/research/re/v5/out/scarce_series.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(sorted(rows, key=lambda r: r["run"]))
    print(len(rows), "weeks read")
