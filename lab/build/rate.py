"""Rolling share of first posts (posted at the win) booked within an hour at the opening fee, as the desk's
capacity_factor() sees it, at fixed minutes of the week; against the final on-time share.
usage: python lab/build/rate.py RUN_DIR ..."""
import json, sys
DAY = 1440
MARKS = [(1, 18), (2, 12), (2, 18), (3, 12)]
for run in sys.argv[1:]:
    s = json.load(open(run + "/summary.json"))["score"]
    posted, fee0, fb = {}, {}, []
    lines = [l.rstrip("\n").split("\t", 2) for l in open(run + "/log.txt", encoding="utf-8")]
    events = []
    for t, code, rest in lines:
        t = int(t)
        if code == "GIG":
            g, o, why = rest.split()[:3]
            if why == "won":
                posted[g] = t; fee0[g] = int(rest.split("fee0=")[1])
        elif code == "BOOKED":
            g, d, fee = rest.split()[:3]
            if g in posted:
                fb.append((posted[g], t, t - posted[g] <= 60 and int(fee) <= fee0[g]))
                del posted[g]
    # unbooked first posts count as slow once an hour has passed
    for g, t0 in posted.items():
        fb.append((t0, t0 + 61, False))
    out = []
    for d, h in MARKS:
        m = d * DAY + h * 60
        done = [ok for (t0, tj, ok) in sorted(fb, key=lambda x: min(x[1], x[0] + 61)) if min(tj, t0 + 61) <= m][-60:]
        rate = (sum(done) + 7) / (len(done) + 10)
        out.append(f"d{d}{h:02d}h {rate:.2f}")
    print(f"{run.split('/')[-2][:14]:14s} {run.split('/')[-1][:6]} ot={s['onTimeShare']:.3f} | " + " ".join(out))
