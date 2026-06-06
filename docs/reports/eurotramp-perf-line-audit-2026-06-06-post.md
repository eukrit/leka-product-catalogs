# Eurotramp Performance-Line Audit — 2026-06-06-post

Scope: **34** handles from `data/curated/eurotramp_performance_line.json`.

## Summary (gaps)
- Products with **no real price** (only usd=0 stub or none): **6/34**
- Products with **zero dimensions** (metadata.length/width/height_cm all 0): **6/34**
- Products with a **non-photo thumbnail** (cert/badge/placeholder/…): **9/34**
- Firestore `vendors/eurotramp/products` docs with **no retail pricing**: **6/34**
- Scope handles **missing** from Medusa: **0**

## Per-product

| group | handle | status | thumb kind | photos/imgs | dims (cm) | medusa price | fs retail |
|---|---|---|---|---|---|---|---|
| booster_and_training | eurotramp-booster-board | published | photo | 5/11 | 93×57×26 | thb=62938,usd=1904,eur=1623,sgd=2423 | yes |
| booster_and_training | eurotramp-booster-board-freestyle | published | unknown | 0/9 | 93×57×26 | thb=71730,usd=2171,eur=1849,sgd=2762 | yes |
| booster_and_training | eurotramp-bungee-longe | published | photo | 5/12 | 0×0×0 | thb=217360,usd=6577,eur=5604,sgd=8368 | yes |
| booster_and_training | eurotramp-somersault-belt-twisting-belt | published | photo | 4/11 | 0×0×0 | thb=27421,usd=830,eur=707,sgd=1056 | yes |
| competition_and_performance_trampolines | eurotramp-albatross | published | photo | 1/1 | 520×305×115 | thb=595420,usd=18017,eur=15351,sgd=22924 | yes |
| competition_and_performance_trampolines | eurotramp-complete-competition-trampoline | published | photo | 7/16 | 0×0×0 | —(usd=0 stub) | no |
| competition_and_performance_trampolines | eurotramp-fivesquare | published | photo | 3/12 | 412×412×150 | —(usd=0 stub) | no |
| competition_and_performance_trampolines | eurotramp-grand-master | published | photo | 16/38 | 520×305×108 | thb=379470,usd=11483,eur=9783,sgd=14610 | yes |
| competition_and_performance_trampolines | eurotramp-ground-trampoline-freestyle | published | photo | 7/16 | 524×311×0 | thb=316040,usd=9563,eur=8148,sgd=12168 | yes |
| competition_and_performance_trampolines | eurotramp-ground-trampoline-indoor | published | photo | 6/13 | 524×316×0 | thb=401096,usd=12137,eur=10341,sgd=15442 | yes |
| competition_and_performance_trampolines | eurotramp-master | published | photo | 12/33 | 457×275×99 | thb=313809,usd=9496,eur=8090,sgd=12082 | yes |
| competition_and_performance_trampolines | eurotramp-ultimate | published | photo | 28/62 | 520×305×115 | thb=503099,usd=15224,eur=12971,sgd=19369 | yes |
| competition_and_performance_trampolines | eurotramp-ultimate-dmt-6x6 | published | photo | 8/36 | 350×190×70 | thb=289572,usd=8762,eur=7466,sgd=11149 | yes |
| competition_and_performance_trampolines | eurotramp-ultimate-freestyle | published | photo | 11/35 | 520×305×115 | thb=483352,usd=14626,eur=12461,sgd=18609 | yes |
| competition_sets | eurotramp-trampoline-set-freestyle | published | photo | 3/5 | 564×919×450 | —(usd=0 stub) | no |
| competition_sets | eurotramp-trampoline-set-one-field | published | feature-badge | 0/10 | 280×460×400 | thb=430651,usd=13031,eur=11103,sgd=16580 | yes |
| competition_sets | eurotramp-trampoline-set-stationary | published | unknown | 0/14 | 1444×1130×400 | thb=430651,usd=13031,eur=11103,sgd=16580 | yes |
| roller_stands_and_transport | eurotramp-anti-slip-plate-dmt | published | photo | 2/9 | 341×185×1 | thb=42772,usd=1294,eur=1103,sgd=1647 | yes |
| roller_stands_and_transport | eurotramp-hdts | published | unknown | 1/13 | 62×42×34 | thb=475095,usd=14376,eur=12249,sgd=18291 | yes |
| roller_stands_and_transport | eurotramp-lifting-roller-stand | published | photo | 9/17 | 80×30×118 | thb=20275,usd=614,eur=523,sgd=781 | yes |
| roller_stands_and_transport | eurotramp-lifting-roller-stand-safe-comfort | published | photo | 4/12 | 90×21×105 | thb=29986,usd=907,eur=773,sgd=1154 | yes |
| roller_stands_and_transport | eurotramp-roller-stand | published | photo | 4/12 | 0×0×0 | thb=14264,usd=432,eur=368,sgd=549 | yes |
| roller_stands_and_transport | eurotramp-run-up-track-dmt | published | unknown | 2/11 | 2250×100×0 | thb=120009,usd=3631,eur=3094,sgd=4620 | yes |
| roller_stands_and_transport | eurotramp-transport-case-hdts | published | unknown | 0/1 | 83×35×29 | thb=36927,usd=1117,eur=952,sgd=1422 | yes |
| safety_envelope | eurotramp-adaption-bars-safety-platform-integral-ultimate | published | photo | 1/1 | 0×0×0 | thb=12509,usd=379,eur=322,sgd=482 | yes |
| safety_envelope | eurotramp-eurotramp-spotting-mat | published | photo | 8/16 | 164×113×14 | thb=41375,usd=1252,eur=1067,sgd=1593 | yes |
| safety_envelope | eurotramp-frame-pads-set-80mm-safety-plus | published | photo | 1/8 | 0×0×0 | thb=158906,usd=4808,eur=4097,sgd=6118 | yes |
| safety_envelope | eurotramp-landing-mat-cover | published | photo | 2/13 | 600×300×30 | thb=84214,usd=2548,eur=2171,sgd=3242 | yes |
| safety_envelope | eurotramp-safety-platforms-and-safety-mats-integral | published | photo | 11/16 | 300×200×20 | thb=120522,usd=3647,eur=3107,sgd=4640 | yes |
| safety_envelope | eurotramp-safety-platforms-and-safety-mats-universal | published | photo | 16/24 | 262×187×115 | thb=106837,usd=3233,eur=2754,sgd=4113 | yes |
| safety_envelope | eurotramp-safety-platforms-universal-freestyle | published | unknown | 0/1 | 262×187×115 | thb=132379,usd=4006,eur=3413,sgd=5097 | yes |
| safety_envelope | eurotramp-set-of-landing-mats-dmt | published | unknown | 0/3 | 300×200×30 | —(usd=0 stub) | no |
| safety_envelope | eurotramp-spieth-ground-safety-mat | published | photo | 2/4 | 300×200×20 | —(usd=0 stub) | no |
| safety_envelope | eurotramp-spotting-mat-freestyle | published | unknown | 0/1 | 164×113×14 | —(usd=0 stub) | no |
