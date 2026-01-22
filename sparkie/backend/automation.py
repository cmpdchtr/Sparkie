import json
import asyncio
from typing import Dict, List
from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError
from playwright_stealth import stealth_async

class CloudAutomator:
    """
    Handles Google Cloud Console interactions using Playwright.
    WARNING: UI Selectors are brittle and subject to change by Google.
    Using this for mass creation violates Google ToS.
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless

    async def create_project_and_key(self, cookies: List[Dict]) -> Dict:
        """
        Flow:
        1. Login via Cookies
        2. Create New Project
        3. Enable Gemini API
        4. Create API Key
        """
        async with async_playwright() as p:
            # Launch User Agent to look like a real browser
            browser = await p.chromium.launch(headless=self.headless, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800},
                locale='en-US'
            )
            
            # Apply stealth scripts to evade basic bot detection
            await stealth_async(context)
            
            # 1. Load Cookies
            await context.add_cookies(cookies)
            page = await context.new_page()

            try:
                # 2. Go to proper console URL to check login
                print("Checking session...")
                await page.goto("https://console.cloud.google.com/", timeout=60000)
                
                if "accounts.google.com/signin" in page.url:
                    raise Exception("Cookies invalid or session expired. Manual login required.")

                # 3. Create Project
                print("Creating Project...")
                project_id = await self._create_project(page)
                
                # 4. Enable API
                print("Enabling Gemini API...")
                await self._enable_api(page, project_id)
                
                # 5. Create Credentials
                print("Generating Key...")
                api_key = await self._create_api_key(page, project_id)
                
                return {
                    "project_id": project_id,
                    "api_key": api_key,
                    "status": "success"
                }

            except Exception as e:
                # Screenshot on failure for debugging
                await page.screenshot(path="error_screenshot.png")
                raise e
            finally:
                await browser.close()

    async def _create_project(self, page: Page) -> str:
        unique_id = f"sparkie-gen-{int(asyncio.get_event_loop().time())}"
        
        # Navigate directly to project creation wizard
        await page.goto("https://console.cloud.google.com/projectcreate")
        
        # Wait for form load
        await page.wait_for_selector("input[name='name']", state="visible")
        
        # Fill Project Name
        await page.fill("input[name='name']", unique_id)
        
        # Wait for checking potential availability (GCP does async validation)
        await page.wait_for_timeout(2000)

        # Click Create
        # Usually looking for a button with text "Create" is fairly safe
        create_btn = page.locator("button:has-text('Create')").first
        await create_btn.click()
        
        # Wait for the creation operation. 
        # Upon success, GCP usually redirects to the Dashboard or shows a notification.
        # We'll wait a significant amount of time for the background process.
        print(f"Waiting for project {unique_id} to be provisioned...")
        await page.wait_for_timeout(25000) 
        
        # We assume the ID is the same as the name we requested, 
        # although GCP might convert it to lowercase-kebab-case automatically.
        return unique_id

    async def _enable_api(self, page: Page, project_id: str):
        # Direct link to API library usually works best to bypass Search UI
        url = f"https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com?project={project_id}"
        await page.goto(url)
        
        try:
            # Check for 'Enable' button. 
            # If 'Manage' or 'API Enabled' is there, we are good.
            enable_btn = page.locator("button:has-text('Enable')")
            
            # fast allow to check if visible without throwing immediately
            if await enable_btn.is_visible(timeout=5000):
                await enable_btn.click()
                print("Clicked Enable...")
                # Wait for the enabling spinner
                await page.wait_for_selector("button:has-text('Manage')", timeout=60000)
            else:
                print("API likely already enabled.")
        except Exception as e:
             print(f"Note: API enable step had issues or was already done: {e}")

    async def _create_api_key(self, page: Page, project_id: str) -> str:
        # Navigate to Credentials page directly
        url = f"https://console.cloud.google.com/apis/credentials?project={project_id}"
        await page.goto(url)
        
        # 1. Click "Create Credentials" (top toolbar usually)
        # Using a more specific selector by text + icon proximity or role is better usually
        # But text is the specific fallback
        await page.click("text=Create Credentials")
        
        # 2. Select "API Key" from the dropdown
        await page.click("text=API key")
        
        # 3. Modal appears with the new key.
        # It usually has a class like 'mat-dialog-container' or similar, but text extraction is best.
        # We look for the input field or code block containing the key.
        
        # Wait for the modal header
        await page.wait_for_selector("text=API key created", timeout=30000)
        
        # The key is usually in a copy-able text area or specific weird angular element.
        # We can try to locate it by the 'Copy' button proximity or simply the content.
        # This is the most brittle part. 
        # Let's try to get the text content of the element displaying the key.
        # Usually it's in a code or span close to user's eye.
        
        # Attempt to grab the key value
        # Strategy: Find the input that holds the key or the text block.
        # Taking a gamble on standard Material Design structure for "Copy to clipboard" parents.
        # Usually there is only 1 visible API key string in this modal.
        
        # This selector looks for a cell/container that likely has the key
        # Assuming the key starts with "AIza" is a strong heuristic for Google Keys.
        try:
             # Wait a sec for animation
            await page.wait_for_timeout(2000)
            
            # Crude scraper: Get all text from the dialog and regex it, 
            # or find the specific element.
            dialog = page.locator("div[role='dialog']")
            key_text = await dialog.inner_text()
            
            import re
            match = re.search(r"AIza[0-9A-Za-z\-_]{35}", key_text)
            if match:
                return match.group(0)
            else:
                 raise Exception("Could not verify key pattern (AIza...) in dialog")

        except Exception as e:
             print(f"Failed to extract key from dialog: {e}")
             # Fallback: maybe just return a marker so we know to check screenshot
             await page.screenshot(path=f"failed_key_{project_id}.png")
             raise e
