"""Early signs of a hard week: per day, how our gigs book (from log.txt), against the week's final on-time share.
usage: python lab/build/hardweek.py data/runs/<tag>/<seed>-L8 ..."""
import json, sys, statistics, collections
DAY = 1440
for run in sys.argv[1:]:
    s = json.load(open(run + "/summary.json"))["score"]
    posted, booked, esc = {}, {}, collections.Counter()
    fee0 = {}
    for line in open(run + "/log.txt", encoding="utf-8"):
        t, code, rest = line.rstrip("\n").split("\t", 2)
        t = int(t)
        if code == "GIG":
            g = rest.split()[0]
            posted[g] = t
        elif code == "BOOKED":
            g = rest.split()[0]
            booked.setdefault(g, t)
        elif code == "ESCALATE":
            esc[t // DAY] += 1
    out = []
    for day in (0, 1, 2):
        gs = [g for g, t in posted.items() if t // DAY == day and (t % DAY) < 18 * 60]
        if not gs:
            out.append("-"); continue
        fast = sum(1 for g in gs if g in booked and booked[g] - posted[g] <= 60) / len(gs)
        never = sum(1 for g in gs if g not in booked) / len(gs)
        out.append(f"d{day}: n={len(gs):3d} fast={fast:.2f} unb={never:.2f} esc={esc[day]:2d}")
    print(f"{run.split('/')[-2]:10s} {run.split('/')[-1][:6]} ot={s['onTimeShare']:.3f} m={s['marginCents']/100:7.0f} | " + " | ".join(out))
