# Rampline — Manual tasks for Eukrit

_Last updated: 2026-05-16, after v2.23.4_

Everything in this file is work that **cannot** be done automatically from
the rampline.com crawl, the GO Drive folder, or the existing pricelist —
it requires either a supplier action, a Medusa admin UI change, or a
visual storefront check.

---

## 1 · Email Rampline for packing-list CBM (blocks B — landed-cost refinement)

**Status (2026-05-16):** Draft is ready in your Gmail Drafts folder.
Subject: *"2025 Rampline per-SKU packing list - request for Thai landed-cost
pricing"*. To `kolbjorn@rampline.no`. Review the body and click Send.

**Why:** v2.22.2 priced 127 Medusa variants at 30 % GM but used a **35 %
flat shipping uplift** in lieu of per-SKU CBM. The crawl, Drive folder,
and past Gmail correspondence (including the June 2025 NIST offer
74670 which only carried a lump-sum airfreight estimate) confirm we
have **no per-SKU packing data anywhere**. Without it, some bulky parks
are likely under-priced and small components over-priced.

**Email draft body (already in Gmail Drafts):**

> Dear Kolbjørn,
>
> I hope all is well at Talgje. We're finalising the Thai retail
> pricing for the 2025 Rampline range and need per-SKU packing data so
> that our landed-cost calculation reflects real freight rather than a
> flat uplift. I've checked our shared Drive folder and our past
> correspondence (including the 74670 offer to NIST Yangma), and we
> don't yet have a complete packing reference.
>
> Could you share, for each of the 127 article codes in the 2025 NOK
> pricelist:
>   - Packed dimensions (L x W x H, in cm) per package
>   - Packed (gross) weight in kg per package
>   - Number of packages per SKU when an item ships in more than one box
>   - Whether the unit ships flat-packed or pre-assembled
>   - Volumetric weight or chargeable weight if you already compute it
>     for DAP quotes
>
> XLSX or CSV is ideal, but any format is fine. If a master packing
> list already exists internally, that would save you the trouble of
> compiling one fresh.
>
> Many thanks,
> Eukrit

**Where to drop the response:**
Save the file under
`leka-product-catalogs/rampline-catalog/data/source/rampline_packing_2025.xlsx`
then re-run:

```
cd leka-product-catalogs
python rampline-catalog/import_pricelist.py --rebuild-landed-from packing_xlsx
python rampline-catalog/sync_variant_prices.py --apply
```

---

## 2 · Artwork + copy for 34 Medusa-only products

These Medusa products have **no rampline.com PDP** — they're either
pricelist-only SKUs, legacy parks, or new sub-products. They will look
empty on the storefront until you supply assets.

| # | Handle | Title | Storefront URL |
|---|---|---|---|
| 1 | rampline-all-in | ALL IN | https://catalogs.leka.studio/rampline/all-in |
| 2 | rampline-balancebuddy-en | BalanceBuddy | https://catalogs.leka.studio/rampline/balancebuddy-en |
| 3 | rampline-balancebuddy-wave | Balancebuddy Wave | https://catalogs.leka.studio/rampline/balancebuddy-wave |
| 4 | rampline-defying-gravity | DEFYING GRAVITY | https://catalogs.leka.studio/rampline/defying-gravity |
| 5 | rampline-dont-step-into-the-water | Don't Step Into The Water | https://catalogs.leka.studio/rampline/dont-step-into-the-water |
| 6 | rampline-double-trouble | DOUBLE TROUBLE | https://catalogs.leka.studio/rampline/double-trouble |
| 7 | rampline-flex-forest | FLEX FOREST | https://catalogs.leka.studio/rampline/flex-forest |
| 8 | rampline-fungi-eng | Fungi | https://catalogs.leka.studio/rampline/fungi-eng |
| 9 | rampline-go | GO | https://catalogs.leka.studio/rampline/go |
| 10 | rampline-jumpstone-en | Jumpstone | https://catalogs.leka.studio/rampline/jumpstone-en |
| 11–14 | rampline-jumpstone-en-{27,3,5,50} | Jumpstone 27/3/5/50 | … |
| 15 | rampline-kangaroo | KANGAROO | https://catalogs.leka.studio/rampline/kangaroo |
| 16 | rampline-marathon-play | MARATHON PLAY | https://catalogs.leka.studio/rampline/marathon-play |
| 17 | rampline-never-stop-playing | NEVER STOP PLAYING | https://catalogs.leka.studio/rampline/never-stop-playing |
| 18 | rampline-play-tag | PLAY TAG | https://catalogs.leka.studio/rampline/play-tag |
| 19 | rampline-pulse-zone | PULSE ZONE | https://catalogs.leka.studio/rampline/pulse-zone |
| 20–23 | rampline-rampball-{35,50,50r,70r} | Rampball 35/50/50R/70R | … |
| 24 | rampline-rampbow | Rampbow | https://catalogs.leka.studio/rampline/rampbow |
| 25 | rampline-rampit | Rampit | https://catalogs.leka.studio/rampline/rampit |
| 26 | rampline-rampit-hopper | Rampit Hopper | https://catalogs.leka.studio/rampline/rampit-hopper |
| 27 | rampline-rampit-storm-en | Rampit Storm | https://catalogs.leka.studio/rampline/rampit-storm-en |
| 28 | rampline-rampit-swing | Rampit TWIN | https://catalogs.leka.studio/rampline/rampit-swing |
| 29 | rampline-rampline-slackline | Rampline slackline | https://catalogs.leka.studio/rampline/rampline-slackline |
| 30 | rampline-spare-parts-for-slackline | Spare parts Rampline | https://catalogs.leka.studio/rampline/spare-parts-for-slackline |
| 31 | rampline-spare-parts-kids-tramp-playground-loop | spare parts KIDS TRAMP TRAMPOLINES | … |
| 32 | rampline-the-floor-is-lava | THE FLOOR IS LAVA | https://catalogs.leka.studio/rampline/the-floor-is-lava |
| 33 | rampline-trampoline-loop-en | Playground Loop | https://catalogs.leka.studio/rampline/trampoline-loop-en |
| 34 | rampline-triple-slack-fun | TRIPLE SLACK FUN | https://catalogs.leka.studio/rampline/triple-slack-fun |

Many of these almost certainly DO exist on rampline.com but the static
crawl + Playwright fallback both missed them (either off-host imgix
URLs with non-matching filenames, or the pages weren't extracted as
products). Easiest path:

1. Open each Medusa admin product page
2. Drag and drop the appropriate Rampline photo + description from the
   2025 pricelist PDF or the Rampline image library
3. Save

If you'd rather batch this: ask Rampline for the official Sales Channel
photo library (one folder per article code) and drop it under
`vendors/rampline-catalog/source-files/sales-channel-photos/<sku>/...`.
I can write a one-off importer when you have those files.

---

## 3 · Storefront visual check (after v2.23.x landings)

**Note (2026-05-16):** URLs without the brand prefix — like
`/rampline/floating-bench` — used to 404 because Medusa stores handles
with the prefix (`rampline-floating-bench`). The bug was fixed in
`leka-website` commit `8886c7d` (now on `main`, deploying via Cloud
Build). Both URL forms should work once the deploy lands. If you're
checking before the deploy completes, use the prefixed form.

Use a real browser to verify (the front-door requires the publishable
key as a request header, only the browser client sets it):

- [ ] Open `https://catalogs.leka.studio/rampline/rampline-floating-bench`
      (or `/rampline/floating-bench` after the deploy) — should show
      14 product photos.
- [ ] Open `https://catalogs.leka.studio/rampline/rampline-take-5` —
      should show the rampline.com 360-viewer photo (1 image, thumb).
- [ ] Open `https://catalogs.leka.studio/rampline/rampline-shockdeck` —
      should show 26 photos.
- [ ] On any Rampline PDP, confirm brand tokens (palette `#B5BC00` /
      logo) render IF the storefront has been wired to read
      `sales_channel.metadata.brand_ci`. If it ignores those tokens, the
      storefront still needs a tweak in `leka-website/catalogs/`.

If brand tokens don't render: file a follow-up task to update the
storefront to consume `sales_channel.metadata.brand_ci` (Medusa Store
API exposes it).

---

## 4 · Confirm the Sunday Drive-sync first run (2026-05-17 06:00 SGT)

The Cloud Scheduler `rampline-drive-sync-weekly` (cron `0 6 * * 0`
Asia/Singapore) is set for tomorrow morning. After it fires:

```
gcloud run jobs executions list \
    --job=rampline-drive-sync \
    --region=asia-southeast1 \
    --limit=2 \
    --project=ai-agents-go
```

Expected: a Sunday 2026-05-17 execution row with status SUCCEEDED.
If FAILED, check the logs:

```
gcloud logging read \
    'resource.type=cloud_run_job AND resource.labels.job_name=rampline-drive-sync' \
    --limit=20 --freshness=2h --format='value(textPayload)' \
    --project=ai-agents-go
```

---

## 5 · Cloud Build trigger smoke test (vendors repo, optional)

You wired the Cloud Build trigger `deploy-rampline-drive-sync` to the
`eukrit/vendors` repo earlier. To confirm it fires:

1. Make any trivial change under `vendors/rampline-catalog/scripts/` on
   `main` (e.g. a comment-only commit).
2. `gcloud builds list --limit=3 --project=ai-agents-go` should show a
   new build kicked off by the push.

Skip this if you don't want to commit a no-op — the next real change
will exercise the trigger anyway.
