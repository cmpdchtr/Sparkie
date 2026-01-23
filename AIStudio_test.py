import json  # <--- 1. Додано імпорт
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

def run_stealth_codegen():
    with sync_playwright() as p:
        # 1. Налаштовуємо браузер
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        
        # 2. Створюємо контекст
        # Прибираємо жорстко заданий User-Agent, щоб він відповідав реальній версії Chrome
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )

        # --- ПОЧАТОК БЛОКУ ЗАВАНТАЖЕННЯ COOKIES ---
        try:
            with open("cookies.json", "r") as f:
                cookies = json.load(f)
                for cookie in cookies:
                    if "sameSite" in cookie:
                        if cookie["sameSite"] == "no_restriction" or cookie["sameSite"] is None:
                            cookie["sameSite"] = "None"
                        elif str(cookie["sameSite"]).lower() == "lax":
                            cookie["sameSite"] = "Lax"
                        elif str(cookie["sameSite"]).lower() == "strict":
                            cookie["sameSite"] = "Strict"
                    if "partitionKey" in cookie:
                        del cookie["partitionKey"]
                context.add_cookies(cookies)
                print("✅ Cookies успішно завантажено з файлу cookies.json")
        except FileNotFoundError:
            print("⚠️ Файл cookies.json не знайдено. Продовжуємо без куків.")
        except Exception as e:
            print(f"❌ Помилка при завантаженні cookies: {e}")
        # --- КІНЕЦЬ БЛОКУ ЗАВАНТАЖЕННЯ COOKIES ---
        
        page = context.new_page()
        
        # 3. Накочуємо Stealth
        stealth_sync(page)
        
        # 4. Відкриваємо сайт
        print("⏳ Переходимо на сайт...")
        # Використовуємо загальну URL без вказівки /u/1/, бо в цьому контексті користувач буде першим (/u/0/)
        page.goto("https://aistudio.google.com/app/api-keys") 
        
        print("🔴 ВІДКРИВАЮ ІНСПЕКТОР. ТИСНИ 'Record' У ВІКНІ!")
        
        # 5. МАГІЯ
        page.pause() 

if __name__ == "__main__":
    run_stealth_codegen()