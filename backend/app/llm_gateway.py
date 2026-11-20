import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException
import litellm

from app.cache import (
    generate_cache_key,
    get_cached_response,
    set_cached_response,
)
from app.config import get_settings

logger = logging.getLogger("app.gateway")


def parse_simulation_header(header_value: Optional[str]) -> Dict[str, int]:
    """
    Parse X-Simulate-Failure header into a dictionary.
    Format: comma-separated <key_id>=<status> pairs; * means every key.
    Statuses allowed: 429, 500, 502, 503.
    """
    if not header_value:
        return {}
    sim_map: Dict[str, int] = {}
    for part in header_value.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip()
            try:
                status_code = int(v)
                if status_code in (429, 500, 502, 503):
                    sim_map[k] = status_code
            except ValueError:
                pass
    return sim_map


def calculate_tokens(model: str, messages: List[Dict[str, str]], reply_text: str, usage: Any) -> Tuple[int, int]:
    """Extract or calculate input_tokens and output_tokens accurately."""
    input_tokens = None
    output_tokens = None
    
    if usage is not None:
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        
    if input_tokens is None:
        try:
            input_tokens = litellm.token_counter(model=model, messages=messages)
        except Exception:
            # Fallback estimation
            total_chars = sum(len(m.get("content", "")) for m in messages)
            input_tokens = max(1, total_chars // 4)
            
    if output_tokens is None:
        try:
            output_tokens = litellm.token_counter(model=model, text=reply_text)
        except Exception:
            output_tokens = max(1, len(reply_text) // 4)
            
    return int(input_tokens), int(output_tokens)


async def execute_chat(
    session_id: str,
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    simulate_failure_header: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute chat completion with LiteLLM caching and multi-key failover.
    
    Returns:
    {
        "reply": str,
        "metadata": {
            "resolution_source": "LIVE_INFERENCE" | "LLM_CACHE",
            "model": str,
            "latency_ms": int,
            "input_tokens": int,
            "output_tokens": int,
            "key_id": str | None,
            "fallback_attempts": int
        }
    }
    """
    settings = get_settings()
    selected_model = model or settings.model
    start_time = time.perf_counter()
    
    # Parse simulation header if enabled
    simulation_active = settings.enable_failure_simulation and bool(simulate_failure_header)
    sim_map = parse_simulation_header(simulate_failure_header) if simulation_active else {}
    
    cache_key = generate_cache_key(selected_model, messages)
    
    # 1. Check cache (only if simulation is NOT actively simulating failures for this request)
    if not simulation_active:
        cached = get_cached_response(cache_key)
        if cached is not None:
            latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
            return {
                "reply": cached["reply"],
                "metadata": {
                    "resolution_source": "LLM_CACHE",
                    "model": cached.get("model", selected_model),
                    "latency_ms": latency_ms,
                    "input_tokens": cached["input_tokens"],
                    "output_tokens": cached["output_tokens"],
                    "key_id": None,
                    "fallback_attempts": 0,
                },
            }

    # 2. Live inference with key failover
    keys = settings.keys
    if not keys:
        logger.error("No API keys configured in key pool.")
        raise HTTPException(status_code=503, detail="all providers unavailable")

    fallback_attempts = 0
    successful_reply: Optional[str] = None
    successful_key_id: Optional[str] = None
    input_tokens = 0
    output_tokens = 0

    for key_info in keys:
        key_id = key_info.id
        api_key = key_info.key
        
        # Check if failure simulation applies to this key
        if simulation_active:
            if "*" in sim_map:
                sim_code = sim_map["*"]
                logger.info(f"Simulation: Key {key_id} failed with status {sim_code} via wildcard (*)")
                fallback_attempts += 1
                continue
            if key_id in sim_map:
                sim_code = sim_map[key_id]
                logger.info(f"Simulation: Key {key_id} failed with status {sim_code}")
                fallback_attempts += 1
                continue
        
        # Attempt live completion with current key
        try:
            response = litellm.completion(
                model=selected_model,
                messages=messages,
                api_key=api_key,
                temperature=0.7,
            )
            
            # Extract reply text
            if hasattr(response, "choices") and len(response.choices) > 0:
                successful_reply = response.choices[0].message.content or ""
            else:
                successful_reply = str(response)
                
            successful_key_id = key_id
            usage = getattr(response, "usage", None)
            input_tokens, output_tokens = calculate_tokens(selected_model, messages, successful_reply, usage)
            
            # Success! Break out of key failover loop
            break
        except Exception as exc:
            # Provider failure: HTTP 429, quota exhausted, 5xx server error, connection drop
            logger.warning(f"Key {key_id} encountered provider error: {exc}. Failing over to next key...")
            fallback_attempts += 1
            continue

    # If all keys failed, return 503
    if successful_reply is None or successful_key_id is None:
        logger.error(f"All {len(keys)} keys failed or exhausted.")
        raise HTTPException(status_code=503, detail="all providers unavailable")

    latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
    
    # Store successful response in cache for identical future requests
    cache_data = {
        "reply": successful_reply,
        "model": selected_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    set_cached_response(cache_key, cache_data)

    return {
        "reply": successful_reply,
        "metadata": {
            "resolution_source": "LIVE_INFERENCE",
            "model": selected_model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "key_id": successful_key_id,
            "fallback_attempts": fallback_attempts,
        },
    }
