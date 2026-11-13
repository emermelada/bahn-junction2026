# v0: starter-like stubs on DEV seeds

**What we saw.** The v0 skeleton with stubs that copy the kit starter (quote list price on the first option, post every car at the typical fee rising 10% an hour to 1.5x, steep fees after `deadline_close`) loses money and is never ranked at level 8.

**The idea.** None yet: this is the floor every later change is compared with, and the proof that the loop, the state fold and the log work.

**The test.** `make check` at commit 8ff8cd7 (tag v0): level 8, seeds dev-01, dev-02, dev-03, and dev-01 again.

| Seed | Margin | On time | Orders | Ranked |
|---|---|---|---|---|
| dev-01 | -€60,375.12 | 41.3% | 831 | no |
| dev-02 | -€73,139.90 | 50.5% | 872 | no |
| dev-03 | -€71,872.79 | 47.2% | 954 | no |
| dev-01 again | -€60,375.12 | 41.3% | 831 | no |

Determinism: both dev-01 runs end with the same margin to the cent and the same state digest (f7330f7135e91960). Replay: folding the saved log rebuilds that digest.

Autopsy of dev-01 (`lab/b/autopsy.py`): late cars come from every town, including Vantaa with 324 drivers within 30 km (45% on time). Capacity and fees, not only empty towns, cause the lateness.

Speed: about 1,900 steps a week at 0.24 s a step on the loaded server, 7.5 minutes a week.

**Keep or kill.** Keep as the floor. Next: win fewer cars (price above list), open fees higher, cap cars per town and day.
