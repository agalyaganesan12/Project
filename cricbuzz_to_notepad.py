# cricbuzz_to_notepad.py
# pip install playwright
# python -m playwright install chromium
# Run:
#   python cricbuzz_to_notepad.py "https://www.cricbuzz.com/live-cricket-scorecard/121681/indw-vs-rsaw-final-icc-womens-world-cup-2025"

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import sys, time, re, pathlib

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.cricbuzz.com/live-cricket-scorecard/121681/indw-vs-rsaw-final-icc-womens-world-cup-2025"
OUT_FILE = "scorecard.txt"

def clean(s: str) -> str:
    return re.sub(r"\s+\n", "\n", re.sub(r"[ \t]+", " ", s or "")).strip()

def autoscroll(page, steps=10, px=1400, pause=0.6):
    for _ in range(steps):
        page.mouse.wheel(0, px)
        time.sleep(pause)

with sync_playwright() as p:
    # Launch a visible browser (Chrome if available)
    try:
        browser = p.chromium.launch(channel="chrome", headless=False, slow_mo=80)
    except Exception:
        browser = p.chromium.launch(headless=False, slow_mo=80)

    page = browser.new_page(viewport={"width": 1360, "height": 900})
    page.goto(URL, timeout=60000)

    # Click "Scorecard" tab if present
    try:
        page.locator("a:has-text('Scorecard')").first.click(timeout=2500)
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    # Dismiss common consent banners (best-effort)
    for sel in ["button:has-text('I Accept')", "button:has-text('Accept')", "button:has-text('AGREE')"]:
        try: page.locator(sel).first.click(timeout=1200)
        except Exception: pass

    # Nudge lazy loading
    autoscroll(page, steps=8)

    # Try to wait until we see something scorecard-ish
    try:
        page.wait_for_selector("text=Batter", timeout=8000)
    except PWTimeout:
        pass  # not all layouts show "Batter" as a header

    # ---- Grab text, innings by innings (preferred) ----
    text_blocks = page.evaluate(
        """
(() => {
  const clean = s => (s || "").replace(/[ \\t]+/g," ").replace(/\\s+\\n/g,"\\n").trim();
  const blocks = [];

  // innings header bars
  const headers = Array.from(document.querySelectorAll(".cb-scrd-hdr-rw"));
  if (headers.length) {
    for (let i = 0; i < headers.length; i++) {
      const h = headers[i];
      let txt = clean(h.innerText);
      // collect sibling nodes until next header
      let cur = h.parentElement?.nextElementSibling;
      let bodyParts = [];
      while (cur && !cur.querySelector?.(".cb-scrd-hdr-rw")) {
        const t = clean(cur.innerText);
        if (t) bodyParts.push(t);
        cur = cur.nextElementSibling;
      }
      blocks.push(`==== ${txt} ====` + "\\n" + bodyParts.join("\\n"));
    }
    return blocks.filter(Boolean);
  }

  // fallback: grab the main column that usually contains scorecard
  const main = document.querySelector(".cb-col.cb-col-67, .cb-col.cb-col-100");
  if (main) return [clean(main.innerText)];

  // last resort: whole body
  return [clean(document.body.innerText)];
})()
        """
    )

    # If nothing meaningful was returned, take entire page text
    if not text_blocks or all(len(b.strip()) < 40 for b in text_blocks):
        full_text = clean(page.inner_text("body"))
        text_blocks = [full_text]

    # Keep only the chunk(s) that contain scorecard words
    filtered = []
    for b in text_blocks:
        low = b.lower()
        if any(k in low for k in ["batter", "batsman", "bowling", "extras", "total", "fall of wickets"]):
            filtered.append(b)

    final_text = "\n\n".join(filtered if filtered else text_blocks)
    pathlib.Path(OUT_FILE).write_text(final_text, encoding="utf-8")
    print(f"\n✅ Scorecard text saved to {OUT_FILE}")

    input("\nDone. Press Enter to close…")
    browser.close()
