"""
generate_dashboards.py — entry point.

Run:   python generate_dashboards.py
Env:   JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (required)
       CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN (optional, fall back to Jira creds)
       CONFLUENCE_SPACE_ID, CONFLUENCE_PARENT_ID (optional, have hardcoded defaults)
       FORCE_REBUILD=1 (optional, bypasses fingerprint check)
       MASTER_CONFLUENCE_PAGE_ID (optional, pushes master dashboard to Confluence)
"""
import json
import os

from config import FORCE_REBUILD
from build_state import load_build_state, save_build_state, is_dirty, mark_clean
from customer_data import fetch_active_customers
from jira import fetch_customer_data
from formatting import compute_health
from confluence import ensure_confluence_page, confluence_page_url
from dashboard_customer import build_customer_html
from dashboard_master import build_master_html


if __name__ == "__main__":
    build_state = load_build_state()
    print(f"  Build state loaded — {len(build_state)} customers have prior fingerprints")
    if FORCE_REBUILD:
        print("  ⚠️  FORCE_REBUILD=1 — all customer pages will be rebuilt")

    CUSTOMERS = fetch_active_customers()
    with open("customers.json", "w") as f:
        json.dump(CUSTOMERS, f, indent=2)
    print(f"  Saved {len(CUSTOMERS)} customers to customers.json")

    customer_results = []
    pages_updated    = False
    rebuilt          = []
    skipped          = []

    for cust in CUSTOMERS:
        cust_id  = cust["id"]
        keyword  = cust["jql_keyword"]
        filename = f"{cust_id}_dashboard.html"
        gh_url   = f"https://vinod-tessell.github.io/cse-confluence/{filename}"
        conf_url = confluence_page_url(cust.get("confluence_page_id", ""))

        # ── Skip unchanged customers ───────────────────────────────────────────
        if not is_dirty(cust_id, keyword, build_state) and os.path.exists(filename):
            cached = build_state.get(f"{cust_id}__meta", {})
            print(f"  ⏭  {cust['name']} — unchanged, skipping rebuild")
            skipped.append(cust["name"])
            customer_results.append({
                "config":       cust,
                "health_key":   cached.get("health_key",   "stable"),
                "health_label": cached.get("health_label", "Stable"),
                "health_color": cached.get("health_color", "#FFC107"),
                "p0_count":     cached.get("p0_count",  0),
                "sup_count":    cached.get("sup_count",  0),
                "eng_count":    cached.get("eng_count",  0),
                "feat_count":   cached.get("feat_count", 0),
                "dashboard_url": conf_url,
            })
            continue

        # ── Full rebuild ───────────────────────────────────────────────────────
        print(f"\n── {cust['name']} ({cust['cso_epic']} · {cust['cso_status']}) ──")
        print(f"  Fetching Jira data (keyword: {keyword})...")
        try:
            data = fetch_customer_data(keyword)
        except Exception as e:
            print(f"  ⚠️  Jira fetch failed: {e}")
            customer_results.append({
                "config": cust, "health_key": "stable", "health_label": "Unknown",
                "health_color": "#5E6C84", "p0_count": 0, "sup_count": 0,
                "eng_count": 0, "feat_count": 0, "dashboard_url": conf_url,
            })
            continue

        print(
            f"  P0/P1:{len(data['p0p1'])}  "
            f"Support(SR):{len(data['support'])}  "
            f"Eng(TS):{len(data['eng_tickets'])}  "
            f"Features:{len(data['features'])}  "
            f"Resolved(30d):{len(data['resolved'])}"
        )

        score, label, color, hk, _pending = compute_health(
            data["p0p1"], data["support"], data["features"],
            data["resolved"], data["eng_tickets"],
        )
        html, page_js = build_customer_html(cust, data)
        with open(filename, "w", encoding="utf-8") as f:
               f.write(html)
        js_filename = filename.replace(".html", ".js")
        with open(js_filename, "w", encoding="utf-8") as f:
               f.write(page_js)
        print(f"  ✅ Written {filename} + {js_filename}")

        page_id = ensure_confluence_page(cust, gh_url)
        if page_id and page_id != cust.get("confluence_page_id", ""):
            cust["confluence_page_id"] = page_id
            pages_updated = True

        conf_url = confluence_page_url(cust.get("confluence_page_id", ""))

        customer_results.append({
            "config":       cust,
            "health_key":   hk,    "health_label": label, "health_color": color,
            "p0_count":     len(data["p0p1"]),
            "sup_count":    len(data["support"]),
            "eng_count":    len(data["eng_tickets"]),
            "feat_count":   len(data["features"]),
            "dashboard_url": conf_url,
        })
        rebuilt.append(cust["name"])

        mark_clean(cust_id, keyword, build_state)
        build_state[f"{cust_id}__meta"] = {
            "health_key":  hk,    "health_label": label, "health_color": color,
            "p0_count":    len(data["p0p1"]),
            "sup_count":   len(data["support"]),
            "eng_count":   len(data["eng_tickets"]),
            "feat_count":  len(data["features"]),
        }
        save_build_state(build_state)   # crash-safe incremental save

    if pages_updated:
        with open("customers.json", "w") as f:
            json.dump(CUSTOMERS, f, indent=2)
        print("\n✅ customers.json updated with new Confluence page IDs")

    print(f"\n── Build summary: {len(rebuilt)} rebuilt, {len(skipped)} skipped ──")
    if rebuilt: print(f"  Rebuilt:  {', '.join(rebuilt)}")
    if skipped: print(f"  Skipped:  {', '.join(skipped)}")

    # ── Master dashboard — always rebuilt (no Jira calls) ─────────────────────
    print("\n── Master Dashboard (always rebuilt) ───────────────────────────")
    master = build_master_html(customer_results)
    with open("master_dashboard.html", "w", encoding="utf-8") as f:
        f.write(master)
    print("✅ master_dashboard.html written")

    master_page_id = os.environ.get("MASTER_CONFLUENCE_PAGE_ID", "").strip()
    if master_page_id:
        ensure_confluence_page(
            {"name": "CSE Portfolio", "confluence_page_id": master_page_id},
            "https://vinod-tessell.github.io/cse-confluence/master_dashboard.html",
        )

    print("\nAll done!")
