# Sparkie

Fault-tolerant layer for Google Gemini API with smart rate-limit handling and automated infrastructure management.

## Project Structure

- `sparkie/client/`: Python library for using Gemini with key rotation.
- `sparkie/backend/`: FastAPI service for managing keys and automating GCP via Playwright.

## Installation

```bash
pip install -r requirements.txt
playwright install
```

## Running the Backend

```bash
     sparkie.backend.main:app --reload
```

## Using the Client

```python
import asyncio
from sparkie.client.core import SparkieClient

async def main():
    # Load keys from backend endpoint or config
    keys = ["KEY_1", "KEY_2", "KEY_3"]
    
    client = SparkieClient(api_keys=keys)
    response = await client.generate_content("Hello, world!")
    print(response.text)

if __name__ == "__main__":
    asyncio.run(main())
```

## Legal Warning

Automating account creation and project generation using UI automation tools (Playwright/Selenium) may violate Google Cloud Platform Terms of Service. Use fastidiously and at your own risk.
