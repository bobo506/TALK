"""Cached, model-specific WorkBuddy ACP capability discovery."""
import threading
import time

from bridges.workbuddy_acp import is_acp_alias, parse_acp_alias, probe_effort_options
from sqlmodel import select
from server.models import RunnerModelChoice, DEFAULT_EFFORT_ORDER

_cache = {}
_lock = threading.Lock()
_inflight = {}  # Entries exist only while a probe is running.


def is_cdp_alias(alias):
    return isinstance(alias, str) and alias.startswith('workbuddy-cdp:')


def cdp_effort_for_facts(session, facts):
    """Read only the exact six-dimensional choice; never infer from a model id."""
    dimensions = ('runner_id', 'model_source', 'provider_id', 'connection_ref', 'model_id', 'model_alias')
    if not facts or facts.get('runtime') != 'workbuddy' or not is_cdp_alias(facts.get('model_alias')):
        return None, None, None
    if any(not isinstance(facts.get(k), str) or not facts[k] for k in dimensions):
        return [], None, 'workbuddy_cdp_choice_not_found'
    query = select(RunnerModelChoice)
    for key in dimensions:
        query = query.where(getattr(RunnerModelChoice, key) == facts[key])
    rows = session.exec(query).all()
    if len(rows) != 1:
        return [], None, 'workbuddy_cdp_choice_not_found'
    capabilities = rows[0].capabilities or []
    options = [x for x in DEFAULT_EFFORT_ORDER if x in ('low', 'high', 'max') and 'effort:' + x in capabilities]
    defaults = [x for x in options if 'effort_default:' + x in capabilities]
    if not options or len(defaults) != 1:
        return [], None, 'workbuddy_cdp_capability_unknown'
    return options, defaults[0], None

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
