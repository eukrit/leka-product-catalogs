"""Quick reconnaissance on the 3 source PDFs in My Drive\\Catalogs GO\\Wisdom Playground.

For each PDF: page count, first 3 pages of text (truncated), product codes detected
on each page via the same regex set used by wisdom-catalog/extract_images.py, total
codes detected, embedded image count.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

SOURCE_DIR = Path(r"C:\Users\Eukrit\My Drive\Catalogs GO\Wisdom Playground")

PATTERNS = [
    r"[A-Z]{2,5}\d?-[A-Z]*\d+[A-Z]*\d*",
    r"QSWP-\d+[A-Z]\d+",
    r"WPPE-\d+[A-Z]?\d*",
    r"SW\d+[A-Z]*-[A-Z]\d+",
    r"SR-\d+",
    r"\d{2,3}-\d{5}(?:-\d+)?",
]


def codes_in_text(text: str) -> set[str]:
    s = set()
    for pat in PATTERNS:
        for m in re.finditer(pat, text):
            c = m.group(0)
            if len(c) >= 5:
                s.add(c)
    return s


def prefix_of(c: str) -> str:
    m = re.match(r"^[A-Z]+", c)
    return m.group(0) if m else "(num)"


def peek(pdf_path: Path) -> None:
    print(f"\n=== {pdf_path.name} ({pdf_path.stat().st_size/1e6:.1f} MB) ===")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  OPEN FAILED: {e}")
        return
    n = len(doc)
    print(f"  pages: {n}")

    all_codes: set[str] = set()
    pages_with_codes = 0
    total_imgs = 0
    sample_pages = []

    for i in range(n):
        page = doc[i]
        text = page.get_text()
        codes = codes_in_text(text)
        if codes:
            pages_with_codes += 1
            all_codes |= codes
        imgs = page.get_images(full=True)
        total_imgs += len(imgs)
        if i < 3:
            sample_pages.append((i + 1, text[:400].replace("\n", " | "), sorted(codes)[:8]))

    pref = Counter(prefix_of(c) for c in all_codes)
    print(f"  distinct codes detected: {len(all_codes)}")
    print(f"  pages with codes: {pages_with_codes}/{n}")
    print(f"  embedded images (raw count): {total_imgs}")
    print(f"  top prefixes: {pref.most_common(15)}")
    print(f"  sample codes: {sorted(list(all_codes))[:25]}")
    print("  first 3 pages preview:")
    for p, txt, cs in sample_pages:
        print(f"    p{p} codes={cs}")
        print(f"    p{p} text: {txt[:250]}")
    doc.close()


def main() -> None:
    pdfs = sorted(SOURCE_DIR.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {SOURCE_DIR}")
    for p in pdfs:
        peek(p)


if __name__ == "__main__":
    main()
