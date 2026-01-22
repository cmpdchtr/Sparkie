# Sparkie

Fault-tolerant Gateway Service for Google Gemini API with smart rate-limit handling and automated infrastructure management.

## Project Structure

- `sparkie/backend/`: The main FastAPI service that acts as both the AI Gateway and Infrastructure Manager.
- `sparkie/client/`: Internal library used by the backend for smart key rotation.

## Installation

```bash
pip install -r requirements.txt
playwright install
pip install playwright-stealth
```

## Running the Service

```bash
uvicorn sparkie.backend.main:app --reload
```

## API Usage

### 1. Upload Account (Admin)
Send cookies from a fresh browser session (use EditThisCookie extension to export).

```http
POST /accounts/upload
Content-Type: application/json

{
  "email": "user@gmail.com",
  "cookies": [{...}, {...}]
}
```

### 2. Generate Keys & Infrastructure (Admin)
Triggers background automation to create project and key.

```http
POST /generate-key/user@gmail.com
```

### 3. Chat with AI (User)
The service balances this request across all available keys.

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "prompt": "Explain Quantum Computing"
}
```

## Legal Warning

Automating account creation and project generation using UI automation tools (Playwright/Selenium) may violate Google Cloud Platform Terms of Service. Use fastidiously and at your own risk.
