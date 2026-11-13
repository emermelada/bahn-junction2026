# Parameter tweaks are exhausted; lane factors are the next lever

**What we saw.** The top teams on the "Saturday 00:00" round make €39-49 an order on 295-360 orders a week; we make €29 on 257. Our ranking weeks: revenue €117-137 an order, driver fee €87-103 (the fee paid is 1.0x the typical fee), won price 1.43-1.54x list.

**Tests against rc3 (b22), 12 rc2 seeds.** None beats rc3 safely:

| Tag | Change | Ranked | Mean delta | Min on-time |
|---|---|---|---|---|
| b26 / b27 | town cap 0.12 / 0.2 | 12 / 12 | -€1,000 / -€500 | 95.8% / 94.1% |
| b28 | learned price | 10 | | 88.9% |
| b29 | weekend fee 1.3x | 9 | | 89.8% |
| b30 | backlog 20 | 7 | | 85.9% |
| b31 / b32 | ratio 1.3 / 1.5 | 8 / 11 | / +€241 | 84.5% / 87.8% |
| b33 | same_day extra 0.1 | 10 | +€351 | 87.9% |
| b38-b40 | ratio 1.5-1.6 with town cap | 12 | -€835 to -€2,147 | 93.7-96.7% |
| b41 / b42 | cost-plus pricing to 1.8x | 9 / 12 | -€684 / -€675 | 87.8% / 93.2% |
| b43-b45 | two-car chains, fee 0.7-0.9x of two | 5-7 | | 83.3-86.7% |

Chains: only 17 pairs a week formed, and holding new cars up to 2 hours to find a partner cost on-time share. Killed as built.

**The lead.** RULES: part of the competitor's price on each lane is the same in every world. Over 443 of our level 8 weeks (272,596 quotes at 1.3-1.75x list), the win rate per lane (359 lanes with 150+ quotes) runs from 11% (p10) through 34% (median) to 62% (p90). At the same price, some lanes win 80-84% (porvoo->rovaniemi, hyvinkaa->kemi, lempaala->kokkola), others 1-5% (jyvaskyla->vantaa, turku->hyvinkaa).

**Next.** A lane table built from all past weeks (not one seed): quote higher on lanes where the competitor is dear, lower or decline where it is cheap. Test on rc2, then fresh seeds.
