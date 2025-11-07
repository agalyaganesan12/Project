# stock_price_scraper_tatapower.py
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import re

TICKER = "TATAPOWER:NSE"  # Tata Power (India)
FINANCE_URL = f"https://www.google.com/finance/quote/{TICKER}?hl=en"

def accept_consent(page):
    # Try common consent buttons (page & iframes); ignore if not present.
    for sel in [
        "button:has-text('I agree')",
        "button:has-text('Accept all')",
        "button:has-text('Accept')",
    ]:
        try:
            page.locator(sel).first.click(timeout=1500); return
        except: pass
    for fsel in [
        "iframe[name='callout']",
        "iframe[src*='consent']",
        "iframe[aria-modal='true']",
    ]:
        try:
            frame = page.frame_locator(fsel)
            frame.locator("button:has-text('I agree'), button:has-text('Accept all'), button:has-text('Accept')").first.click(timeout=1500); return
        except: pass

def get_price_on_finance(page):
    # Primary: stable Google Finance price selector
    price = page.locator("div.YMlKec.fxKbKc").first
    try:
        price.wait_for(timeout=8000)
        return price.inner_text().strip()  # e.g., ₹372.45
    except PWTimeout:
        # Fallback: first rupee-looking number
        m = re.search(r"₹\s?([\d,]+(?:\.\d+)?)", page.content())
        return f"₹{m.group(1)}" if m else None

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)   # set True to hide the browser
        context = browser.new_context(locale="en-IN") # INR formatting
        page = context.new_page()

        page.goto(FINANCE_URL, timeout=60000)
        accept_consent(page)

        price = get_price_on_finance(page)
        if price:
            print(f"\n✅ Tata Power (NSE) Stock Price: {price}\n")
        else:
            print("\n❌ Could not locate the price. UI may have changed.\n")

        browser.close()

if __name__ == "__main__":
    main()
