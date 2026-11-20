import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import litellm
from litellm.caching.caching import Cache

logger = logging.getLogger("app.cache")

# Global LiteLLM cache reference
_litellm_cache: Optional[Cache] = None
# Local fallback memory cache in case LiteLLM Cache methods vary
_fallback_cache: Dict[str, Dict[str, Any]] = {}


def init_cache() -> Cache:
    """Initialize LiteLLM built-in cache."""
    global _litellm_cache
    try:
        _litellm_cache = Cache(type="local")
        litellm.cache = _litellm_cache
        litellm.enable_cache(type="local")
        logger.info("LiteLLM local cache enabled successfully.")
    except Exception as exc:
        logger.warning(f"Could not initialize litellm.Cache(type='local'): {exc}")
        _litellm_cache = None
    return _litellm_cache


def generate_cache_key(model: str, messages: List[Dict[str, str]]) -> str:
    """
    Generate deterministic cache key based on model + full message list.
    Cache key: model + the full message list sent to the LLM (system prompt + history + new message).
    """
    # Normalize message list to only role and content
    normalized = [{"role": str(m.get("role", "")), "content": str(m.get("content", ""))} for m in messages]
    raw_payload = json.dumps({"model": model, "messages": normalized}, sort_keys=True)
    digest = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
    return f"llm_cache:{digest}"


def get_cached_response(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached response from LiteLLM cache or fallback store."""
    global _litellm_cache, _fallback_cache
    
    # 1. Try LiteLLM built-in cache if available
    if _litellm_cache is not None:
        try:
            val = _litellm_cache.get_cache(cache_key)
            if val is not None:
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except Exception:
                        pass
                elif isinstance(val, dict):
                    return val
        except Exception as e:
            logger.debug(f"litellm.cache.get_cache error: {e}")
            
    # 2. Try fallback memory cache
    return _fallback_cache.get(cache_key)


def set_cached_response(cache_key: str, data: Dict[str, Any]) -> None:
    """Store response in LiteLLM cache and fallback store."""
    global _litellm_cache, _fallback_cache
    
    # 1. Save in fallback memory cache
    _fallback_cache[cache_key] = data
    
    # 2. Save in LiteLLM cache
    if _litellm_cache is not None:
        try:
            _litellm_cache.set_cache(cache_key, data)
        except Exception as e:
            logger.debug(f"litellm.cache.set_cache error: {e}")


def clear_cache() -> None:
    """Helper for testing: reset cache."""
    global _fallback_cache, _litellm_cache
    _fallback_cache.clear()
    if _litellm_cache is not None:
        try:
            if hasattr(_litellm_cache, "cache"):
                _litellm_cache.cache.clear()
        except Exception:
            pass
