import json
from typing import List, Dict
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import init_db, AsyncSessionLocal, GoogleAccount, CloudProject, ApiKey
from .automation import CloudAutomator
from ..client.core import SparkieClient

app = FastAPI(title="Sparkie Backend & Gateway")

# Global Client Instance
sparkie_client = SparkieClient(api_keys=[])

# Pydantic Models
class AccountUpload(BaseModel):
    email: str
    cookies: List[Dict]

class KeyResponse(BaseModel):
    key: str
    project_id: str

class ChatRequest(BaseModel):
    prompt: str
    stream: bool = False

# Dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def reload_keys(db: AsyncSession):
    """Reloads keys from DB into the running client."""
    result = await db.execute(select(ApiKey.key).where(ApiKey.is_active == True))
    keys = result.scalars().all()
    sparkie_client.update_keys(keys)

@app.on_event("startup")
async def startup():
    await init_db()
    # Initial Key Load
    async with AsyncSessionLocal() as db:
        await reload_keys(db)

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    Proxy endpoint for AI generation. 
    Uses internal SparkieClient for rotation and fault tolerance.
    """
    try:
        # Note: In a real app, map 'request' parameters to gemini params properly
        response = await sparkie_client.generate_content(request.prompt)
        return {
            "text": response.text,
            "backend_model": "gemini-pro"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.post("/accounts/upload")
async def upload_account(payload: AccountUpload, db: AsyncSession = Depends(get_db)):
    """Uploads authentication cookies for a Google Account."""
    # Check existing
    result = await db.execute(select(GoogleAccount).where(GoogleAccount.email == payload.email))
    existing = result.scalar_one_or_none()
    
    cookies_str = json.dumps(payload.cookies)
    
    if existing:
        existing.cookies_json = cookies_str
        existing.is_active = True
    else:
        new_account = GoogleAccount(email=payload.email, cookies_json=cookies_str)
        db.add(new_account)
    
    await db.commit()
    return {"status": "stored", "email": payload.email}

async def run_generation_task(account_id: int):
    """Background task to run Playwright automation."""
    async with AsyncSessionLocal() as db:
        # Retrieve account
        result = await db.execute(select(GoogleAccount).where(GoogleAccount.id == account_id))
        account = result.scalar_one_or_none()
        
        if not account or not account.is_active:
            return

        automator = CloudAutomator(headless=True)
        try:
            cookies = json.loads(account.cookies_json)
            print(f"Starting automation for {account.email}")
            
            result_data = await automator.create_project_and_key(cookies)
            
            # Save results
            new_project = CloudProject(
                id=result_data["project_id"],
                account_id=account.id
            )
            new_key = ApiKey(
                key=result_data["api_key"],
                project_id=result_data["project_id"]
            )
            
            db.add(new_project)
            db.add(new_key)
            account.project_count += 1
            await db.commit()
            print(f"Key generated successfully: {result_data['api_key'][:10]}...")
            
            # Refresh Global Client
            await reload_keys(db)

        except Exception as e:
            print(f"Automation failed: {e}")
            # Logic to mark account as failed or invalid cookies could go here

@app.post("/generate-key/{email}")
async def trigger_generation(email: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Triggers the background Playwright task to create a key."""
    result = await db.execute(select(GoogleAccount).where(GoogleAccount.email == email))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
        
    background_tasks.add_task(run_generation_task, account.id)
    return {"status": "queued", "message": "Key generation started in background"}

@app.post("/admin/refresh-keys")
async def manual_refresh(db: AsyncSession = Depends(get_db)):
    """Force reloads keys from DB into memory."""
    await reload_keys(db)
    return {"status": "refreshed", "active_keys_count": len(sparkie_client._active_keys)}

@app.get("/keys", response_model=List[str])
async def get_active_keys(db: AsyncSession = Depends(get_db)):
    """Returns a list of active keys for the Sparkie Client."""
    result = await db.execute(select(ApiKey.key).where(ApiKey.is_active == True))
    keys = result.scalars().all()
    return keys

@app.get("/api/v1/keys/stats")
async def get_keys_stats():
    """Returns usage statistics for the in-memory keys."""
    return sparkie_client.get_stats()

