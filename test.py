from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

def run():
    with sync_playwright() as p:
        # Launch the browser
        # headless=True usually triggers bot detection, but stealth helps hide it.
        browser = p.chromium.launch(headless=False)
        
        # Create a new page
        page = browser.new_page()

        # APPLY STEALTH (Crucial Step)
        # This must be done before navigating to the page
        stealth_sync(page)

        # Navigate to a bot detection test site
        page.goto("https://bot.sannysoft.com/")

        # Wait a bit to ensure tests run
        page.wait_for_timeout(5000)

        # Take a screenshot to verify results
        page.screenshot(path="stealth_result.png", full_page=True)
        print("Screenshot saved as stealth_result.png")
        
        print("🔴 ВІДКРИВАЮ ІНСПЕКТОР. ТИСНИ 'Record' У ВІКНІ!")
        page.pause() 

        browser.close()

if __name__ == "__main__":
    run()