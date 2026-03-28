"""
confluence.py — Confluence page management (create, update, URL helpers).
"""
import json
import requests

from config import (
    CONFLUENCE_BASE, CONFLUENCE_SPACE, CONFLUENCE_PARENT,
    conf_auth, conf_headers, CACHE_BUST,
)


def get_confluence_page_version(page_id):
    r = requests.get(
        f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{page_id}",
        auth=conf_auth,
        headers={"Accept": "application/json"},
    )
    return r.json().get("version", {}).get("number", 1) if r.status_code == 200 else 1


def confluence_page_url(page_id):
    if not page_id:
        return "#"
    return f"https://tessell.atlassian.net/wiki/spaces/CSE/pages/{page_id}"


def ensure_confluence_page(cust, dashboard_url):
    """Create or update the Confluence page that iframes the given dashboard URL."""
    page_id    = cust.get("confluence_page_id", "").strip()
    busted_url = f"{dashboard_url}?v={CACHE_BUST}"
    iframe_body = json.dumps({
        "version": 1, "type": "doc", "content": [{"type": "extension", "attrs": {
            "extensionType": "com.atlassian.confluence.macro.core",
            "extensionKey": "iframe",
            "parameters": {"macroParams": {
                "src":         {"value": busted_url},
                "width":       {"value": "100%"},
                "height":      {"value": "900px"},
                "frameborder": {"value": "0"},
                "scrolling":   {"value": "yes"},
            }},
            "layout": "full-width",
        }}],
    })

    if page_id:
        ver = get_confluence_page_version(page_id)
        r   = requests.put(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{page_id}",
            auth=conf_auth, headers=conf_headers,
            json={
                "id": page_id, "status": "current",
                "title": f"{cust['name']} — Customer Dashboard",
                "version": {"number": ver + 1},
                "body": {"representation": "atlas_doc_format", "value": iframe_body},
            },
        )
        if r.status_code in (200, 204):
            print(f"  ✅ Updated Confluence page {page_id} (v{ver + 1})")
        else:
            print(f"  ⚠️  Could not update {page_id}: {r.status_code} {r.text[:120]}")
        return page_id
    else:
        r = requests.post(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages",
            auth=conf_auth, headers=conf_headers,
            json={
                "spaceId":  CONFLUENCE_SPACE,
                "parentId": CONFLUENCE_PARENT,
                "status":   "current",
                "title":    f"{cust['name']} — Customer Dashboard",
                "body":     {"representation": "atlas_doc_format", "value": iframe_body},
            },
        )
        if r.status_code == 200:
            new_id = r.json()["id"]
            cust["confluence_page_id"] = new_id
            print(f"  ✅ Created Confluence page {new_id} for {cust['name']}")
            return new_id
        else:
            print(f"  ⚠️  Could not create page for {cust['name']}: {r.status_code} {r.text[:200]}")
            return ""
