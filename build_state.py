"""
build_state.py — incremental build fingerprinting so unchanged customers are skipped.
"""
import json
import hashlib
import os
import requests

from config import JIRA_BASE, BUILD_STATE_FILE, FORCE_REBUILD, auth, headers


def load_build_state():
    if os.path.exists(BUILD_STATE_FILE):
        try:
            with open(BUILD_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_build_state(state):
    with open(BUILD_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def customer_fingerprint(keyword):
    """Lightweight hash of the 5 most-recently-updated tickets for this customer."""
    try:
        r = requests.get(
            f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
            params={
                "jql": f'project in (TS, SR) AND text ~ "{keyword}" AND updated >= -7d ORDER BY updated DESC',
                "maxResults": 5,
                "fields": "updated,status,priority",
            },
        )
        if r.status_code != 200:
            return None
        issues = r.json().get("issues", [])
        sig = "|".join(
            f"{i['key']}:{i['fields'].get('updated', '')}:"
            f"{i['fields'].get('status', {}).get('name', '')}:"
            f"{(i['fields'].get('priority') or {}).get('name', '')}"
            for i in issues
        )
        return hashlib.md5(sig.encode()).hexdigest()
    except Exception:
        return None


def is_dirty(cust_id, keyword, build_state):
    """Return True if this customer needs a rebuild. Caches fingerprint for mark_clean."""
    if FORCE_REBUILD:
        return True
    fp = customer_fingerprint(keyword)
    build_state[f"{cust_id}__fp_cache"] = fp   # stash so mark_clean reuses it
    if fp is None:
        return True
    return build_state.get(cust_id) != fp


def mark_clean(cust_id, keyword, build_state):
    """Persist fingerprint — reuses the cached value from is_dirty to avoid a second API call."""
    fp = build_state.pop(f"{cust_id}__fp_cache", None) or customer_fingerprint(keyword)
    if fp:
        build_state[cust_id] = fp
