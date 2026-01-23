import json
import asyncio
import logging
from typing import Dict, List
from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError
from playwright_stealth import Stealth

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CloudAutomator:
    """
    Handles Google Cloud Console interactions using Playwright.
    WARNING: UI Selectors are brittle and subject to change by Google.
    Using this for mass creation violates Google ToS.
    """
    
    def __init__(self, headless: bool = False):
        self.headless = headless

    def _sanitize_cookies(self, cookies: List[Dict]) -> List[Dict]:
        """Cleans and maps cookies from EditThisCookie format to Playwright."""
        sanitized = []
        for c in cookies:
            sc = c.copy()
            # 1. Remap expirationDate -> expires
            if "expirationDate" in sc:
                sc["expires"] = sc.pop("expirationDate")
            
            # 2. Fix sameSite values
            if "sameSite" in sc:
                ss = sc["sameSite"]
                if ss == "no_restriction":
                    sc["sameSite"] = "None"
                elif ss is None:
                    # Remove null sameSite to allow defaults
                    del sc["sameSite"]
                elif isinstance(ss, str):
                    # Capitalize valid values: lax -> Lax, strict -> Strict
                    capitalized = ss.capitalize()
                    if capitalized in ["Lax", "Strict", "None"]:
                         sc["sameSite"] = capitalized
                    else:
                        del sc["sameSite"]
            
            # 3. Clean unsupported keys (Playwright is strict sometimes)
            keys_to_remove = ["hostOnly", "session", "firstPartyDomain", "partitionKey", "storeId", "id"]
            for k in keys_to_remove:
                if k in sc:
                    del sc[k]
                    
            sanitized.append(sc)
        return sanitized

    async def create_project_and_key(self, cookies: List[Dict]) -> Dict:
        """
        Flow:
        1. Login via Cookies to AI Studio
        2. Handle Terms of Service (if new account)
        3. Create API Key > Create in new project
        4. Extract Key
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless, args=["--disable-blink-features=AutomationControlled"])
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800},
                locale='en-US'
            )
            
            stealth = Stealth()
            await stealth.apply_stealth_async(context)
            
            clean_cookies = self._sanitize_cookies(cookies)
            await context.add_cookies(clean_cookies)
            page = await context.new_page()

            try:
                logger.info("Navigating to AI Studio API Key page...")
                await page.goto("https://aistudio.google.com/app/apikey", timeout=60000)
                
                # Check for login redirect
                if "accounts.google.com/signin" in page.url:
                    logger.error("Session invalid. Redirected to login page.")
                    raise Exception("Cookies invalid or session expired. Manual login required.")

                # Handle potential onboarding / ToS
                await self._handle_onboarding(page)

                # Create Key
                logger.info("Starting Key Generation...")
                api_key = await self._generate_key_aistudio(page)
                
                # We don't get a visible project ID easily in this flow, 
                # but valid key is what matters. We can assign a placeholder.
                project_id = "aistudio-auto-gen" 

                return {
                    "project_id": project_id,
                    "api_key": api_key,
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Automation caught exception: {e}")
                await page.screenshot(path="error_aistudio_final.png")
                logger.info("Saved error_aistudio_final.png")
                raise e
            finally:
                logger.info("Closing browser...")
                await browser.close()

    async def _handle_onboarding(self, page: Page):
        """Handles 'Terms of Service' or 'Get Started' prompts if they appear."""
        try:
            # Check for generic "Consent" or "Terms" headers
            # Often appearing in a modal or overlay
            # Example: "I agree to the Generative AI Additional Terms of Service"
            
            # Wait briefly to see if we are blocked
            await page.wait_for_load_state("networkidle", timeout=5000)

            # Check for ToS Checkbox
            checkbox = page.locator("mat-checkbox") 
            # Very generic, but usually only one on the consent screen
            
            if await checkbox.count() > 0 and await page.locator("text=Terms of Service").is_visible():
                logger.info("ToS Screen detected. Accepting...")
                
                # Check all checkboxes (sometimes there are 2: ToS and Email updates)
                for cb in await checkbox.all():
                    if not await cb.is_checked():
                        await cb.click()
                        await page.wait_for_timeout(500)
                
                # Look for "Continue" or "Next" button
                btns = ["button:has-text('Continue')", "button:has-text('Agree')", "button:has-text('Next')"]
                for b in btns:
                    if await page.locator(b).is_visible():
                        await page.click(b)
                        logger.info(f"Clicked {b}")
                        break
                
                await page.wait_for_timeout(3000) # Wait for transition
            else:
                logger.info("No obvious ToS screen detected. Proceeding...")

        except Exception as e:
            logger.warning(f"Onboarding check skipped or failed (non-fatal): {e}")

    async def _generate_key_aistudio(self, page: Page) -> str:
        # 1. Find 'Create API key' button
        # Usually checking for the main action button
        create_btn = page.locator("button:has-text('Create API key')")
        
        # Sometimes there's a prompt 'Get API key'
        if not await create_btn.is_visible():
             create_btn = page.locator("button:has-text('Get API key')")

        if not await create_btn.is_visible(timeout=10000):
            # It might be captured in a different UI state or already have keys
            # Try searching loosely
            pass

        logger.info("Clicking Create API Key...")
        await create_btn.first.click()

        # 2. Wait for the Options Modal "Create API key in new project"
        # It might also just create it if no projects exist, but usually asks.
        
        try:
            # Look for the specific option to create in a NEW project
            # This avoids selecting an existing one by mistake
            new_proj_btn = page.locator("text=Create API key in new project")
            await new_proj_btn.wait_for(state="visible", timeout=10000)
            logger.info("Selecting 'Create in new project'...")
            await new_proj_btn.click()
        except TimeoutError:
            logger.warning("Did not see 'Create in new project' option. Maybe it auto-created?")
            # If we don't see the option, maybe it just went straight to creation (if 0 projects)
            pass

        # 3. Wait for Key Display
        logger.info("Waiting for key generation...")
        
        # The key is usually shown in a copyable text field or code block
        # Valid pattern: AIza...
        
        # We'll wait for the text to appear
        try:
            # Wait for any element containing the pattern
            # Using a regex-based locator is powerful here
            key_locator = page.locator("text=/AIza[0-9A-Za-z\\-_]{35}/")
            await key_locator.wait_for(state="visible", timeout=60000)
            
            key_text = await key_locator.inner_text()
            
            # Clean up if it grabbed surrounding text
            import re
            match = re.search(r"AIza[0-9A-Za-z\-_]{35}", key_text)
            if match:
                key = match.group(0)
                logger.info(f"Key generated: {key[:10]}...")
                return key
            else:
                raise Exception("Found text but regex failed to extract API key")

        except Exception as e:
            await page.screenshot(path="debug_key_generation_failed.png")
            logger.error(f"Failed to find key: {e}")
            raise
