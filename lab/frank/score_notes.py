"""Score the note reader against the reveal truth in data/notes_corpus.jsonl.

Run: ./.venv/Scripts/python lab/frank/score_notes.py [corpus.jsonl] [--quiet]
Per field: exact accuracy and 'safe' share (ready: ours >= truth; hours: ours inside truth;
deadline: ours <= truth), booleans: precision / recall. Then per language, then every miss.
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from spreadbot.notes import read_note  # noqa: E402
from note_cases import check  # noqa: E402  (same folder)

WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FIELDS = ["ready", "payment", "pickup_hours", "delivery_hours", "deadline", "manual", "plates", "summer"]
BOOLS = {"payment", "manual", "plates", "summer"}


def t(m: int | None) -> str:
    return "-" if m is None else f"{WD[(m // 1440) % 7]}{m // 1440} {m % 1440 // 60:02d}:{m % 60:02d}"


def hh(h: tuple[int, int] | None) -> str:
    return "private" if h is None else f"{h[0] // 60}:{h[0] % 60:02d}-{h[1] // 60}:{h[1] % 60:02d}"


def pair(h: dict | None) -> tuple[int, int] | None:
    return None if h is None else (h["opens"], h["closes"])


def compare(leg: dict, ours, truth: dict) -> dict[str, tuple]:
    """field -> (ours, truth, exact, safe) for one leg."""
    stated = leg["pickup"]["window"]["from"]
    r_ours = max(stated, ours.ready_at or stated)
    r_true = max(stated, truth["readyAt"], truth["releasedAt"] or 0)
    out = {"ready": (r_ours, r_true, r_ours == r_true, r_ours >= r_true)}
    paid = truth["releasedAt"] is not None
    out["payment"] = (ours.after_payment, paid, ours.after_payment == paid, ours.after_payment >= paid)
    for f, stop, th in (("pickup_hours", "pickup", "pickupHours"), ("delivery_hours", "delivery", "deliveryHours")):
        o = getattr(ours, f) or pair(leg[stop]["hours"])
        tr = pair(truth[th])
        safe = o == tr or (o is not None and tr is not None and o[0] >= tr[0] and o[1] <= tr[1])
        out[f] = (o, tr, o == tr, safe)
    d_o, d_t = ours.deadline, truth["noteDeadline"]
    never = 1 << 30  # no deadline = later than any
    out["deadline"] = (d_o, d_t, d_o == d_t, (never if d_o is None else d_o) <= (never if d_t is None else d_t))
    for f, attr, key in (("manual", "manual", "manualGearbox"), ("plates", "plates", "needsPlates"),
                         ("summer", "summer_tyres", "summerTyres")):
        o, tr = getattr(ours, attr), bool(truth[key])
        out[f] = (o, tr, o == tr, o >= tr)
    return out


def fmt(field: str, v) -> str:
    if field in ("ready", "deadline"):
        return t(v)
    if field.endswith("hours"):
        return hh(v)
    return str(v)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else "data/notes_corpus.jsonl"
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    exact = collections.Counter()
    safe = collections.Counter()
    n = collections.Counter()
    conf = {f: collections.Counter() for f in BOOLS}  # tp/fp/fn
    lang_ok = collections.Counter()
    lang_n = collections.Counter()
    misses = []
    uncertain = uncertain_missed = 0
    t0 = time.perf_counter()
    reads = [read_note(r["request"]) for r in rows]
    per_note_ms = (time.perf_counter() - t0) * 1000 / max(1, len(rows))
    for i, (row, ours) in enumerate(zip(rows, reads)):
        req, truth = row["request"], row["truth"]
        lang = req["note"]["language"]
        assert len(ours) == len(req["legs"]) == len(truth), f"line {i}: leg count"
        note_ok = True
        for k, (leg, o, tr) in enumerate(zip(req["legs"], ours, truth)):
            for f, (vo, vt, ex, sf) in compare(leg, o, tr).items():
                n[f] += 1
                exact[f] += ex
                safe[f] += sf
                if f in BOOLS:
                    conf[f]["tp"] += vo and vt
                    conf[f]["fp"] += vo and not vt
                    conf[f]["fn"] += vt and not vo
                if not ex:
                    note_ok = False
                    misses.append((f, i, k, lang, req["note"]["text"], fmt(f, vo), fmt(f, vt), sf, o.uncertain))
        uncertain += any(o.uncertain for o in ours)
        uncertain_missed += any(o.uncertain for o in ours) and not note_ok
        lang_n[lang] += 1
        lang_ok[lang] += note_ok
    print(f"{len(rows)} notes, {sum(len(r['truth']) for r in rows)} legs, {per_note_ms:.3f} ms per note\n")
    print(f"{'field':16s} {'exact':>7s} {'safe':>7s}   precision  recall")
    for f in FIELDS:
        line = f"{f:16s} {100 * exact[f] / n[f]:6.1f}% {100 * safe[f] / n[f]:6.1f}%"
        if f in BOOLS:
            c = conf[f]
            p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 1.0
            r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 1.0
            line += f"   {100 * p:7.1f}%  {100 * r:6.1f}%  (tp {c['tp']}, fp {c['fp']}, fn {c['fn']})"
        print(line)
    print("\nnotes fully right, by language:")
    for lang in sorted(lang_n):
        print(f"  {lang}: {lang_ok[lang]}/{lang_n[lang]} = {100 * lang_ok[lang] / lang_n[lang]:.1f}%")
    total_ok = sum(lang_ok.values())
    print(f"  all: {total_ok}/{len(rows)} = {100 * total_ok / len(rows):.1f}%")
    print(f"\nflagged uncertain: {uncertain} notes ({uncertain_missed} of them with a miss)")
    total, rule_misses = check()
    print(f"hand-written rule cases (held out, lab/frank/note_cases.py): {total - len(rule_misses)}/{total}")
    for m in rule_misses:
        print("  RULE MISS", m)
    if "--quiet" in sys.argv:
        return
    print(f"\nmisses ({len(misses)}):")
    for f, i, k, lang, text, vo, vt, sf, unc in sorted(misses):
        tag = ("safe" if sf else "UNSAFE") + (", flagged" if unc else "")
        print(f"  [{f}] #{i} leg{k} {lang}: {text!r}\n      ours {vo} | truth {vt} ({tag})")


if __name__ == "__main__":
    main()
