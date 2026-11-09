"""Cached, model-specific WorkBuddy ACP capability discovery."""
import threading
import time

from bridges.workbuddy_acp import is_acp_alias, parse_acp_alias, probe_effort_options

_cache = {}
_lock = threading.Lock()
_inflight = {}  # Entries exist only while a probe is running.

def describe_model(model_id):
    """只读取未过期缓存，不启动探测。"""
    if not is_acp_alias(model_id):
        return [], None
    with _lock:
        cached = _cache.get(model_id)
        if cached and time.monotonic() < cached[0]:
            return list(cached[1]), cached[2] if len(cached) > 2 else None
    return [], None

def options_for_model(model_id):
    if not is_acp_alias(model_id):
        return []
    while True:
        with _lock:
            cached = _cache.get(model_id)
            if cached and time.monotonic() < cached[0]:
                return list(cached[1])
            event = _inflight.get(model_id)
            if event is None:
                event = _inflight[model_id] = threading.Event()
                break
        event.wait()

    try:
        try:
            options = probe_effort_options(parse_acp_alias(model_id))
            error, ttl = None, 600
        except Exception as exc:
            options, error, ttl = [], getattr(exc, "code", None) or "workbuddy_acp_probe_failed", 60
        with _lock:
            _cache[model_id] = (time.monotonic() + ttl, tuple(options), error)
        return list(options)
    finally:
        with _lock:
            del _inflight[model_id]
            event.set()

def runtime_options_for_facts(facts):
    facts = facts or {}
    if facts.get('runtime') != 'workbuddy' or not is_acp_alias(facts.get('model_alias')):
        return None, None
    options = options_for_model(facts['model_alias'])
    return (options, 'adapter') if options else (None, None)
