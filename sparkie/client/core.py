import asyncio
import random
import time
from typing import List, Optional, Dict
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, GoogleAPICallError

class KeyStats:
    def __init__(self, key: str):
        self.key = key
        self.is_active = True
        self.last_used = 0.0
        self.usage_count = 0
        self.consecutive_errors = 0

class SparkieClient:
    def __init__(self, api_keys: List[str], model_name: str = "gemini-pro"):
        self._model_name = model_name
        self._lock = asyncio.Lock()
        self.update_keys(api_keys)

    def update_keys(self, api_keys: List[str]):
        """Updates the internal key pool dynamically."""
        if not api_keys:
            # If no keys provided, we can either raise or set empty. 
            # Ideally logs a warning.
            self._keys = {}
            self._active_keys = []
            return

        # Preserve stats for existing keys, add new ones
        new_keys_dict = {}
        for k in api_keys:
            if hasattr(self, "_keys") and k in self._keys:
                new_keys_dict[k] = self._keys[k]
            else:
                new_keys_dict[k] = KeyStats(k)
        
        self._keys = new_keys_dict
        self._active_keys = list(self._keys.keys())
        random.shuffle(self._active_keys)
        print(f"[Sparkie] Loaded {len(self._active_keys)} keys.")

    def get_stats(self) -> List[Dict]:
        """Returns statistics for all managed keys."""
        stats = []
        for k, v in self._keys.items():
            stats.append({
                "key_preview": f"{k[:10]}...",
                "usage_count": v.usage_count,
                "consecutive_errors": v.consecutive_errors,
                "last_used_timestamp": v.last_used,
                "is_active": v.is_active
            })
        return stats

    def _get_next_key(self) -> str:
        """
        Smart selection strategy:
        Prioritizes keys that have:
        1. No recent errors (ResourceExhausted).
        2. Lower usage count (freshness).
        3. Longest time since last use (cooling off).
        """
        now = time.time()
        
        # Sort keys by "suitability"
        # 1. Recovery: If a key had an error recently (e.g. < 60s ago), it's deprioritized
        # 2. Usage: Prefer keys with lower total usage
        # 3. Last Used: Prefer keys that haven't been used recently
        
        def key_priority(k: str):
            stats = self._keys[k]
            # Penalty for recent errors (exponential backoff simulation)
            error_penalty = 0
            if stats.consecutive_errors > 0:
                time_since_error = now - stats.last_used
                # If error was recent (less than 1 minute * num_errors), high penalty
                if time_since_error < (60 * stats.consecutive_errors):
                    error_penalty = 1000 * stats.consecutive_errors

            # Basic freshness score: Usage count
            freshness_score = stats.usage_count
            
            # Recency bias: We want keys used long ago to have lower score (better rank)
            # time.time() is large, so we subtract last_used. 
            # Larger (now - last_used) = Played long ago.
            # We want smallest score first. So we want to subtract the "idle time".
            recency_score = - (now - stats.last_used) 

            return error_penalty + freshness_score + recency_score

        # Sort the active keys list based on the calculated priority
        self._active_keys.sort(key=key_priority)
        
        # Pick the best one
        key = self._active_keys[0]
        
        # Update its metadata immediately so it doesn't get picked by another thread instantly
        # (Though we have a lock, conceptually this is 'claiming' it)
        self._keys[key].last_used = now
        
        return key

    async def _handle_error(self, key: str, error: Exception):
        """Marks key as bad if rate limited."""
        stats = self._keys[key]
        stats.consecutive_errors += 1
        stats.last_used = time.time()
        
        if isinstance(error, ResourceExhausted):
            # 429: Push this key to the very end of the queue or temporarily disable
            print(f"[Sparkie] Key {key[:10]}... exhausted. Rotating.")
            # In a real scenario, you might move it to a 'cooldown' list
            # For now, we rely on the list rotation to just try the next one
        else:
            print(f"[Sparkie] API Error with key {key[:10]}...: {error}")

    async def generate_content(self, prompt: str, **kwargs):
        """
        Wrapper for gemini.generate_content that rotates keys on failure.
        """
        if not self._active_keys:
             raise RuntimeError("No API keys available in Sparkie. Please upload account cookies to generate keys.")

        attempts = 0
        max_attempts = len(self._active_keys) * 2 # Allow cycling twice through all keys

        while attempts < max_attempts:
            async with self._lock:
                current_key = self._get_next_key()
            
            genai.configure(api_key=current_key)
            model = genai.GenerativeModel(self._model_name)
            
            try:
                # Assuming simple text generation for MVP
                # Offload the blocking call to a thread if synchronous, 
                # but google-generativeai has async support now in newer versions.
                # using await model.generate_content_async if available
                
                response = await model.generate_content_async(prompt, **kwargs)
                
                # Success
                self._keys[current_key].usage_count += 1
                self._keys[current_key].consecutive_errors = 0
                return response

            except ResourceExhausted as e:
                await self._handle_error(current_key, e)
                attempts += 1
                # Immediate retry with next key loop
                continue
                
            except Exception as e:
                # Other errors (500, etc)
                await self._handle_error(current_key, e)
                attempts += 1
                # Add small backoff for non-429 errors
                await asyncio.sleep(0.5) 

        raise RuntimeError("All Sparkie keys exhausted or service unavailable.")

# Example Usage
if __name__ == "__main__":
    async def main():
        # Mock keys
        client = SparkieClient(api_keys=["key1", "key2", "key3"])
        try:
            # This will fail with mock keys obviously
            res = await client.generate_content("Hello")
            print(res.text)
        except Exception as e:
            print(f"Final failure: {e}")

    asyncio.run(main())
