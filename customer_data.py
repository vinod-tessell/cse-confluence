"""
customer_data.py — customer reference data, static overrides, name normalisation,
                   Confluence page discovery, epic parsing, and customer entry builder.
"""
import re
import json
import requests

from config import (
    CONFLUENCE_BASE, CONFLUENCE_PARENT, REFERENCE_PAGE_ID,
    conf_auth, LOGO_PALETTE, STATIC_OVERRIDES, DISPLAY_NAME_MAP,
    JIRA_BASE, auth, headers,
)


# ── Confluence reference page ─────────────────────────────────────────────────

def load_customer_reference():
    """Fetch Customer Reference Data page from Confluence → dict keyed by name fragment."""
    try:
        r = requests.get(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{REFERENCE_PAGE_ID}",
            auth=conf_auth,
            headers={"Accept": "application/json"},
            params={"body-format": "atlas_doc_format"},
        )
        if r.status_code != 200:
            print(f"  ⚠️  Could not fetch reference page: {r.status_code}")
            return {}

        body = r.json().get("body", {})
        adf  = body.get("atlas_doc_format", {}).get("value", "{}")
        doc  = json.loads(adf) if isinstance(adf, str) else adf

        ref_data = {}

        def walk(node):
            if not isinstance(node, dict):
                return
            if node.get("type") == "tableRow":
                cells = node.get("content", [])
                texts = []
                for cell in cells:
                    cell_text = ""
                    for block in cell.get("content", []):
                        for inline in block.get("content", []):
                            if inline.get("type") == "text":
                                cell_text += inline.get("text", "")
                    texts.append(cell_text.strip())
                if len(texts) >= 3 and texts[0] and texts[0].lower() != "customer key" and not texts[0].startswith("_"):
                    key = texts[0].lower().strip()
                    ref_data[key] = {
                        "tam_secondary": texts[1] if texts[1] not in ("—", "-", "") else "",
                        "exec_sponsor":  texts[2] if texts[2] not in ("—", "-", "") else "",
                    }
            for child in node.get("content", []):
                walk(child)

        walk(doc)
        print(f"  📋 Customer reference loaded from Confluence — {len(ref_data)} entries")
        return ref_data

    except Exception as e:
        print(f"  ⚠️  Customer reference fetch failed: {e}")
        return {}


def lookup_reference(name, ref_data):
    """Fuzzy-match customer name against reference keys."""
    nl = name.lower()
    for key, rec in ref_data.items():
        if key and key in nl:
            return rec
    return {}


# ── Static override helpers ───────────────────────────────────────────────────

def find_override(name):
    """Match customer name against STATIC_OVERRIDES — substring on lowercase."""
    nl = name.lower()
    for key, override in STATIC_OVERRIDES.items():
        if key in nl:
            return override
    return {}


# ── Name normalisation ────────────────────────────────────────────────────────

def first_name(name):
    if not name:
        return name
    if "&" in name:
        return " ".join(w.capitalize() for w in name.split())
    return name.split()[0].capitalize()


def normalise_display_name(raw):
    """Map raw Jira displayName → first name only."""
    if not raw:
        return "—"
    mapped = DISPLAY_NAME_MAP.get(raw, raw)
    return first_name(mapped)


# ── Confluence page map (auto-discovery) ──────────────────────────────────────

_CONFLUENCE_PAGE_MAP: dict = {}


def fetch_confluence_page_map():
    """Fetch all child pages of CONFLUENCE_PARENT → name fragment → page_id map."""
    global _CONFLUENCE_PAGE_MAP
    try:
        r = requests.get(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{CONFLUENCE_PARENT}/children",
            auth=conf_auth,
            headers={"Accept": "application/json"},
            params={"limit": 50},
        )
        if r.status_code != 200:
            print(f"  ⚠️  Could not fetch Confluence children: {r.status_code}")
            return
        pages = r.json().get("results", [])
        for p in pages:
            title   = p.get("title", "")
            page_id = p.get("id", "")
            name_part = title.replace("— Customer Dashboard", "").replace("- Customer Dashboard", "").strip().lower()
            _CONFLUENCE_PAGE_MAP[name_part] = page_id
            first_word = name_part.split()[0] if name_part.split() else name_part
            _CONFLUENCE_PAGE_MAP[first_word] = page_id
        print(f"  📄 Confluence page map loaded — {len(pages)} pages under Customer Portfolio")
    except Exception as e:
        print(f"  ⚠️  Confluence page map fetch failed: {e}")


def lookup_confluence_page_id(customer_name):
    override = find_override(customer_name)
    if override.get("confluence_page_id"):
        return override["confluence_page_id"]
    nl = customer_name.lower()
    for key, page_id in _CONFLUENCE_PAGE_MAP.items():
        if key and key in nl:
            return page_id
    return ""


# ── Epic description parser ───────────────────────────────────────────────────

def parse_epic_description(description):
    if not description:
        return {}
    text = description.lower()

    cloud  = "Azure" if "azure" in text else "AWS"
    region = "eastus" if cloud == "Azure" else "us-east-1"

    for hint, val in {
        "us-east-1": "us-east-1", "us-east-2": "us-east-2",
        "us-west-1": "us-west-1", "us-west-2": "us-west-2",
        "eu-west-1": "eu-west-1", "eu-central-1": "eu-central-1",
        "ap-southeast-1": "ap-southeast-1", "ap-south-1": "ap-south-1",
        "eastus": "eastus", "westeurope": "westeurope",
        "centralus": "centralus", "southeastasia": "southeastasia",
    }.items():
        if hint in text:
            region = val
            break

    engines = []
    for keywords, label in [
        (["oracle"],                           "Oracle"),
        (["mysql"],                            "MySQL"),
        (["postgresql", "postgres"],           "PostgreSQL"),
        (["sql server", "mssql", "sqlserver"], "SQL Server"),
    ]:
        if any(k in text for k in keywords):
            engines.append(label)
    if not engines:
        engines = ["Oracle"]

    portal_url = ""
    m = re.search(r'https?://[\w.-]+\.tessell\.com[^\s\)\"\']*', description)
    if m:
        portal_url = m.group(0).rstrip(".,;")

    return {"cloud": cloud, "region": region, "engines": engines, "portal_url": portal_url}


# ── Lifecycle helpers ─────────────────────────────────────────────────────────

def status_to_phase(status_name):
    s = status_name.lower()
    if "to do"    in s: return "Onboarding"
    if "progress" in s: return "Implementation"
    if "done"     in s: return "Production"
    return "Stabilisation"


def make_initials(name):
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()


# ── Customer entry builder ────────────────────────────────────────────────────

def build_customer_entry(idx, name, status, owner, epic_key, description="", phase_override=None, ref_data=None):
    ref_data     = ref_data or {}
    phase        = phase_override or status_to_phase(status)
    palette      = LOGO_PALETTE[idx % len(LOGO_PALETTE)]
    override     = find_override(name)
    parsed       = parse_epic_description(description)
    ref          = lookup_reference(name, ref_data)
    slug         = override.get("id") or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    conf_page_id = override.get("confluence_page_id") or lookup_confluence_page_id(name)

    tam_primary   = normalise_display_name(owner) if owner else (ref.get("tam_secondary") or "—")
    tam_secondary = first_name(ref.get("tam_secondary", "") or "")
    exec_sponsor  = first_name(ref.get("exec_sponsor",  "") or "")

    if tam_secondary and tam_secondary == tam_primary:
        tam_secondary = ""

    return {
        "id":                 slug,
        "name":               name,
        "initials":           make_initials(name),
        "logo_color":         palette["logo_color"],
        "logo_bg":            palette["logo_bg"],
        "cloud":              override.get("cloud")   or parsed.get("cloud",   "AWS"),
        "region":             override.get("region")  or parsed.get("region",  "us-east-1"),
        "engines":            override.get("engines") or parsed.get("engines", ["Oracle"]),
        "phase":              phase,
        "tam_primary":        tam_primary,
        "tam_secondary":      tam_secondary,
        "exec_sponsor":       exec_sponsor,
        "portal_url":         override.get("portal_url") or parsed.get("portal_url", ""),
        "confluence_page_id": conf_page_id,
        "jql_keyword":        override.get("jql_keyword", name),
        "active":             True,
        "ticket_history":     [],
        "pulse":              [],
        "cso_epic":           epic_key,
        "cso_status":         status,
    }


# ── Active customer discovery ─────────────────────────────────────────────────

def fetch_active_customers():
    ref_data = load_customer_reference()
    print(f"  📋 Customer reference loaded — {len(ref_data)} entries")
    fetch_confluence_page_map()

    print("Tier 1: Fetching active implementation epics (CSO != Done)...")
    r1 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": "project = CSO AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC",
                "maxResults": 50, "fields": "summary,status,assignee,description,created,updated"},
    )
    r1.raise_for_status()
    tier1_epics = r1.json().get("issues", [])
    print(f"  Found {len(tier1_epics)} active implementation epics")

    print("Tier 2: Fetching completed epics with live TS/SR activity...")
    r2 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": "project = CSO AND issuetype = Epic AND statusCategory = Done ORDER BY updated DESC",
                "maxResults": 100, "fields": "summary,status,assignee,description,created,updated"},
    )
    r2.raise_for_status()
    done_epics = r2.json().get("issues", [])

    tier2_epics = []
    for epic in done_epics:
        name     = (epic["fields"].get("summary") or "").strip()
        override = find_override(name)
        keyword  = override.get("jql_keyword", name)
        try:
            check = requests.get(
                f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": (f'project in (TS, SR) AND text ~ "{keyword}" '
                                f'AND statusCategory != Done AND updated >= -30d'),
                        "maxResults": 1, "fields": "summary"},
            )
            if check.status_code == 200 and check.json().get("total", 0) > 0:
                tier2_epics.append(epic)
        except Exception:
            pass

    def extract(epic):
        f    = epic["fields"]
        desc = f.get("description") or ""
        if isinstance(desc, dict):
            parts = []
            for block in desc.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        parts.append(inline.get("text", ""))
            desc = " ".join(parts)
        return (
            (f.get("summary") or "").strip(),
            f.get("status", {}).get("name", "To Do"),
            (f.get("assignee") or {}).get("displayName", ""),
            desc,
        )

    seen_names, customers = set(), []
    for idx, epic in enumerate(tier1_epics):
        name, status, owner, desc = extract(epic)
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            customers.append(build_customer_entry(idx, name, status, owner, epic["key"], desc, ref_data=ref_data))

    for epic in tier2_epics:
        name, _, owner, desc = extract(epic)
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            customers.append(build_customer_entry(
                len(customers), name, "Done", owner, epic["key"], desc,
                phase_override="Steady State", ref_data=ref_data,
            ))

    print(f"\n  Total customers: {len(customers)}")
    return customers
