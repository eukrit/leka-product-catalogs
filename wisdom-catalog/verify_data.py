"""
Verification script: cross-check Firestore data against source Excel files.
Checks: product codes, descriptions, prices, image URLs accessibility.
"""
import os
import sys
import json
import re
import requests
import pandas as pd
from collections import defaultdict

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\eukri\OneDrive\Documents\Claude Code\Credentials Claude Code\ai-agents-go-9b4219be8c01.json"
from google.cloud import firestore

DOWNLOADS_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\Wisdom Slack Downloads"
REPORT_DIR = r"C:\Users\eukri\OneDrive\Documents\Claude Code\2026 Product Catalogs Claude\docs"

db = firestore.Client(project="ai-agents-go", database="leka-product-catalogs")


def load_firestore_products():
    products = {}
    for doc in db.collection("products_wisdom").stream():
        products[doc.id] = doc.to_dict()
    return products


def load_excel_china():
    path = f"{DOWNLOADS_DIR}/2025-11-07 2025 price list for whole Catalog.xlsx"
    df = pd.read_excel(path, sheet_name="2025 Price for China Catalog", header=0)
    return df


def load_excel_us():
    path = f"{DOWNLOADS_DIR}/Wisdom US catalog price list 20250528.xlsx"
    df = pd.read_excel(path, sheet_name="Table 1", header=2)
    return df


def verify_product_codes(fs_products, excel_china, excel_us):
    """Check all Excel product codes exist in Firestore."""
    print("=" * 60)
    print("VERIFICATION 1: Product Codes")
    print("=" * 60)

    china_codes = set(excel_china["Item Code"].dropna().astype(str).str.strip())
    us_codes = set(excel_us["Item Code"].dropna().astype(str).str.strip())
    fs_codes = set(fs_products.keys())

    # China catalog
    china_missing = china_codes - fs_codes
    china_extra = fs_codes - china_codes - us_codes
    print(f"\nChina Catalog ({len(china_codes)} codes):")
    print(f"  In Firestore: {len(china_codes & fs_codes)}")
    print(f"  Missing from Firestore: {len(china_missing)}")
    if china_missing:
        print(f"  Sample missing: {list(china_missing)[:10]}")

    # US catalog
    us_missing = us_codes - fs_codes
    print(f"\nUS Catalog ({len(us_codes)} codes):")
    print(f"  In Firestore: {len(us_codes & fs_codes)}")
    print(f"  Missing from Firestore: {len(us_missing)}")
    if us_missing:
        print(f"  Sample missing: {list(us_missing)[:10]}")

    print(f"\nFirestore total: {len(fs_codes)}")
    print(f"  From China only: {len(fs_codes & china_codes - us_codes)}")
    print(f"  From US only: {len(fs_codes & us_codes - china_codes)}")
    print(f"  In both: {len(fs_codes & china_codes & us_codes)}")

    return {
        "china_total": len(china_codes),
        "china_in_fs": len(china_codes & fs_codes),
        "china_missing": len(china_missing),
        "us_total": len(us_codes),
        "us_in_fs": len(us_codes & fs_codes),
        "us_missing": len(us_missing),
        "fs_total": len(fs_codes),
    }


def verify_descriptions(fs_products, excel_china):
    """Check product descriptions match between Excel and Firestore."""
    print("\n" + "=" * 60)
    print("VERIFICATION 2: Product Descriptions")
    print("=" * 60)

    mismatches = []
    checked = 0
    matched = 0

    for _, row in excel_china.iterrows():
        code = str(row.get("Item Code", "")).strip()
        if not code or code not in fs_products:
            continue
        checked += 1

        excel_desc = str(row.get("Description", "")).strip()
        fs_desc = str(fs_products[code].get("description", "")).strip()

        if excel_desc.lower() == fs_desc.lower():
            matched += 1
        else:
            # Check if it's a close match (contains)
            if excel_desc.lower() in fs_desc.lower() or fs_desc.lower() in excel_desc.lower():
                matched += 1
            else:
                mismatches.append({
                    "code": code,
                    "excel": excel_desc[:60],
                    "firestore": fs_desc[:60],
                })

    print(f"  Checked: {checked}")
    print(f"  Matched: {matched} ({matched*100//checked}%)")
    print(f"  Mismatched: {len(mismatches)}")
    if mismatches:
        print(f"\n  Sample mismatches:")
        for m in mismatches[:10]:
            print(f"    {m['code']}:")
            print(f"      Excel:     {m['excel']}")
            print(f"      Firestore: {m['firestore']}")

    return {"checked": checked, "matched": matched, "mismatches": len(mismatches)}


def verify_prices(fs_products, excel_china, excel_us):
    """Check prices match between Excel and Firestore."""
    print("\n" + "=" * 60)
    print("VERIFICATION 3: Prices (FOB USD)")
    print("=" * 60)

    price_diffs = []
    checked = 0
    matched = 0
    close = 0

    for _, row in excel_china.iterrows():
        code = str(row.get("Item Code", "")).strip()
        if not code or code not in fs_products:
            continue

        excel_price = row.get("2025 FOB price (USD)")
        if pd.isna(excel_price):
            continue

        try:
            excel_price = float(excel_price)
        except (ValueError, TypeError):
            continue

        checked += 1
        fs_price = fs_products[code].get("pricing", {}).get("fob_usd")

        if fs_price is None:
            price_diffs.append({"code": code, "excel": excel_price, "fs": None, "diff": "missing"})
            continue

        diff = abs(excel_price - fs_price)
        if diff < 0.01:
            matched += 1
        elif diff < 1.0:
            close += 1
            matched += 1
        else:
            pct = diff / excel_price * 100 if excel_price > 0 else 0
            price_diffs.append({
                "code": code,
                "excel": round(excel_price, 2),
                "fs": round(fs_price, 2),
                "diff": round(diff, 2),
                "pct": round(pct, 1),
            })

    print(f"  Checked: {checked}")
    print(f"  Exact/close match: {matched} ({matched*100//max(checked,1)}%)")
    print(f"  Price differences: {len(price_diffs)}")
    if price_diffs:
        print(f"\n  Sample differences:")
        for p in sorted(price_diffs, key=lambda x: x.get("pct", 0) if isinstance(x.get("pct"), (int, float)) else 0, reverse=True)[:10]:
            print(f"    {p['code']}: Excel ${p['excel']} vs Firestore ${p['fs']} (diff: {p.get('diff','n/a')}, {p.get('pct','n/a')}%)")

    return {"checked": checked, "matched": matched, "diffs": len(price_diffs)}


def verify_images(fs_products):
    """Check image URLs are accessible and correctly formatted."""
    print("\n" + "=" * 60)
    print("VERIFICATION 4: Image URLs")
    print("=" * 60)

    with_images = 0
    without_images = 0
    total_images = 0
    broken_urls = []
    sample_checked = 0
    sample_ok = 0

    for code, data in fs_products.items():
        imgs = data.get("images", [])
        if imgs:
            with_images += 1
            total_images += len(imgs)
        else:
            without_images += 1

    print(f"  Products with images: {with_images}")
    print(f"  Products without images: {without_images}")
    print(f"  Total image references: {total_images}")

    # Sample check: test 50 random image URLs
    import random
    products_with_imgs = [(code, data) for code, data in fs_products.items() if data.get("images")]
    sample = random.sample(products_with_imgs, min(50, len(products_with_imgs)))

    print(f"\n  Checking {len(sample)} random image URLs...")
    for code, data in sample:
        for img in data["images"][:1]:  # check primary only
            url = img.get("url", "")
            sample_checked += 1
            try:
                resp = requests.head(url, timeout=5)
                if resp.status_code == 200:
                    sample_ok += 1
                else:
                    broken_urls.append({"code": code, "url": url, "status": resp.status_code})
            except Exception as e:
                broken_urls.append({"code": code, "url": url, "error": str(e)[:50]})

    print(f"  Sample URLs OK: {sample_ok}/{sample_checked}")
    if broken_urls:
        print(f"  Broken URLs ({len(broken_urls)}):")
        for b in broken_urls[:5]:
            print(f"    {b['code']}: {b.get('status', b.get('error', 'unknown'))}")

    # Check image naming format
    correctly_named = 0
    for code, data in products_with_imgs:
        for img in data["images"]:
            fname = img["url"].split("/")[-1]
            if code in fname or code.replace("-", "_") in fname:
                correctly_named += 1
                break

    print(f"\n  Images named with product code: {correctly_named}/{with_images}")

    return {
        "with_images": with_images,
        "without_images": without_images,
        "total_images": total_images,
        "sample_ok": sample_ok,
        "sample_checked": sample_checked,
        "broken": len(broken_urls),
        "correctly_named": correctly_named,
    }


def generate_html_report(code_results, desc_results, price_results, img_results):
    """Generate HTML verification report."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Verification Report — Wisdom Catalog</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{ --purple: #8003FF; --navy: #182557; --cream: #FFF9E6; --green: #16a34a; --red: #dc2626; --amber: #FFA900; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Manrope',sans-serif; background:#F5F3EF; color:var(--navy); }}
.header {{ background:var(--navy); padding:40px; }}
.header h1 {{ color:var(--cream); font-size:28px; font-weight:800; }}
.header p {{ color:var(--cream); opacity:0.6; margin-top:4px; font-size:14px; }}
.container {{ max-width:960px; margin:0 auto; padding:32px 24px; }}
.card {{ background:white; border-radius:16px; padding:24px; margin-bottom:24px; box-shadow:0 2px 8px rgba(24,37,87,0.08); }}
.card h2 {{ font-size:18px; font-weight:700; margin-bottom:16px; border-left:4px solid var(--purple); padding-left:12px; }}
.stat-row {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:12px; }}
.stat {{ padding:12px 20px; background:var(--cream); border-radius:10px; text-align:center; min-width:120px; }}
.stat-value {{ font-size:24px; font-weight:800; }}
.stat-label {{ font-size:11px; opacity:0.6; margin-top:2px; }}
.pass {{ color: var(--green); }}
.warn {{ color: var(--amber); }}
.fail {{ color: var(--red); }}
.badge {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; color:white; }}
.badge-pass {{ background:var(--green); }}
.badge-warn {{ background:var(--amber); color:var(--navy); }}
.badge-fail {{ background:var(--red); }}
table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
th,td {{ text-align:left; padding:8px 12px; border-bottom:1px solid rgba(24,37,87,0.08); font-size:13px; }}
th {{ font-weight:600; opacity:0.6; font-size:11px; text-transform:uppercase; }}
.footer {{ text-align:center; padding:32px; opacity:0.4; font-size:12px; }}
</style>
</head>
<body>
<div class="header">
  <div style="max-width:960px;margin:0 auto;">
    <h1>Data Verification Report — Wisdom Catalog v1.3.0</h1>
    <p>Generated: 2026-03-23 | Cross-checked against source Excel files</p>
  </div>
</div>
<div class="container">

  <div class="card">
    <h2>Product Codes</h2>
    <div class="stat-row">
      <div class="stat"><div class="stat-value pass">{code_results['china_in_fs']}</div><div class="stat-label">China in Firestore</div></div>
      <div class="stat"><div class="stat-value {'pass' if code_results['china_missing']==0 else 'warn'}">{code_results['china_missing']}</div><div class="stat-label">China Missing</div></div>
      <div class="stat"><div class="stat-value pass">{code_results['us_in_fs']}</div><div class="stat-label">US in Firestore</div></div>
      <div class="stat"><div class="stat-value {'pass' if code_results['us_missing']==0 else 'warn'}">{code_results['us_missing']}</div><div class="stat-label">US Missing</div></div>
    </div>
    <span class="badge badge-{'pass' if code_results['china_missing']==0 and code_results['us_missing']==0 else 'warn'}">
      {'PASS' if code_results['china_missing']==0 else f"{code_results['china_missing']} codes missing"}
    </span>
  </div>

  <div class="card">
    <h2>Product Descriptions</h2>
    <div class="stat-row">
      <div class="stat"><div class="stat-value">{desc_results['checked']}</div><div class="stat-label">Checked</div></div>
      <div class="stat"><div class="stat-value pass">{desc_results['matched']}</div><div class="stat-label">Matched</div></div>
      <div class="stat"><div class="stat-value {'pass' if desc_results['mismatches']==0 else 'warn'}">{desc_results['mismatches']}</div><div class="stat-label">Mismatched</div></div>
    </div>
    <span class="badge badge-{'pass' if desc_results['mismatches']<=5 else 'warn'}">
      {desc_results['matched']*100//max(desc_results['checked'],1)}% match rate
    </span>
  </div>

  <div class="card">
    <h2>Prices (FOB USD)</h2>
    <div class="stat-row">
      <div class="stat"><div class="stat-value">{price_results['checked']}</div><div class="stat-label">Checked</div></div>
      <div class="stat"><div class="stat-value pass">{price_results['matched']}</div><div class="stat-label">Matched</div></div>
      <div class="stat"><div class="stat-value {'pass' if price_results['diffs']==0 else 'warn'}">{price_results['diffs']}</div><div class="stat-label">Different</div></div>
    </div>
    <span class="badge badge-{'pass' if price_results['diffs']<=5 else 'warn'}">
      {price_results['matched']*100//max(price_results['checked'],1)}% match rate
    </span>
  </div>

  <div class="card">
    <h2>Product Images</h2>
    <div class="stat-row">
      <div class="stat"><div class="stat-value">{img_results['with_images']}</div><div class="stat-label">With Images</div></div>
      <div class="stat"><div class="stat-value">{img_results['without_images']}</div><div class="stat-label">Without Images</div></div>
      <div class="stat"><div class="stat-value">{img_results['total_images']}</div><div class="stat-label">Total Images</div></div>
      <div class="stat"><div class="stat-value pass">{img_results['sample_ok']}/{img_results['sample_checked']}</div><div class="stat-label">URLs OK (sampled)</div></div>
    </div>
    <div class="stat-row">
      <div class="stat"><div class="stat-value {'pass' if img_results['broken']==0 else 'fail'}">{img_results['broken']}</div><div class="stat-label">Broken URLs</div></div>
      <div class="stat"><div class="stat-value">{img_results['correctly_named']}</div><div class="stat-label">Named by Code</div></div>
    </div>
    <span class="badge badge-{'pass' if img_results['broken']==0 else 'fail'}">
      {'All URLs OK' if img_results['broken']==0 else f"{img_results['broken']} broken URLs"}
    </span>
  </div>

</div>
<div class="footer">Wisdom Catalog Verification Report &copy; 2026 | Generated by Claude Code</div>
</body>
</html>"""

    report_path = os.path.join(REPORT_DIR, "wisdom-catalog-verification.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML report saved: {report_path}")


def main():
    print("Loading data...")
    fs_products = load_firestore_products()
    excel_china = load_excel_china()
    excel_us = load_excel_us()
    print(f"  Firestore: {len(fs_products)} products")
    print(f"  China Excel: {len(excel_china)} rows")
    print(f"  US Excel: {len(excel_us)} rows")

    code_results = verify_product_codes(fs_products, excel_china, excel_us)
    desc_results = verify_descriptions(fs_products, excel_china)
    price_results = verify_prices(fs_products, excel_china, excel_us)
    img_results = verify_images(fs_products)

    print("\n" + "=" * 60)
    print("OVERALL SUMMARY")
    print("=" * 60)
    print(f"  Codes:        {code_results['china_in_fs']+code_results['us_in_fs']} matched, {code_results['china_missing']+code_results['us_missing']} missing")
    print(f"  Descriptions: {desc_results['matched']}/{desc_results['checked']} matched ({desc_results['matched']*100//max(desc_results['checked'],1)}%)")
    print(f"  Prices:       {price_results['matched']}/{price_results['checked']} matched ({price_results['matched']*100//max(price_results['checked'],1)}%)")
    print(f"  Images:       {img_results['with_images']} products have images, {img_results['sample_ok']}/{img_results['sample_checked']} URLs OK")

    generate_html_report(code_results, desc_results, price_results, img_results)


if __name__ == "__main__":
    main()
