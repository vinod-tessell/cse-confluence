import os, json, re, requests, hashlib
from datetime import datetime, timezone
from requests.auth import HTTPBasicAuth

JIRA_BASE  = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_API_TOKEN"]

CONFLUENCE_BASE  = os.environ.get("CONFLUENCE_BASE_URL", JIRA_BASE)
CONFLUENCE_EMAIL = os.environ.get("CONFLUENCE_EMAIL", JIRA_EMAIL)
CONFLUENCE_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", JIRA_TOKEN)
CONFLUENCE_SPACE = os.environ.get("CONFLUENCE_SPACE_ID", "1225719811")
CONFLUENCE_PARENT= os.environ.get("CONFLUENCE_PARENT_ID", "1990557712")

# ── Force-rebuild flag: set env var FORCE_REBUILD=1 to ignore build state ─────
FORCE_REBUILD = os.environ.get("FORCE_REBUILD", "0") == "1"

# ── Build state file — tracks last-built fingerprint per customer ──────────────
BUILD_STATE_FILE = "build_state.json"

auth         = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
conf_auth    = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN)
headers      = {"Accept": "application/json"}
conf_headers = {"Accept": "application/json", "Content-Type": "application/json"}

CACHE_BUST = int(datetime.now(timezone.utc).timestamp())

# ── Customer reference data — sourced from Confluence page ────────────────────
# Maintained at: https://tessell.atlassian.net/wiki/spaces/CSE/pages/2166030367
# The page contains a table with columns: Customer Key | TAM Secondary | Exec Sponsor
# Keys are lowercase first-word fragments of the CSO epic name.
REFERENCE_PAGE_ID = "2166030367"

def load_customer_reference():
    """
    Fetch the Customer Reference Data page from Confluence and parse the
    markdown table into a dict keyed by customer name fragment.
    Falls back to {} on any error so the build never hard-fails.
    """
    try:
        r = requests.get(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{REFERENCE_PAGE_ID}",
            auth=conf_auth,
            headers={"Accept": "application/json"},
            params={"body-format": "atlas_doc_format"}
        )
        if r.status_code != 200:
            print(f"  ⚠️  Could not fetch reference page: {r.status_code}")
            return {}

        # Extract plain text from ADF body
        body = r.json().get("body", {})
        adf  = body.get("atlas_doc_format", {}).get("value", "{}")
        doc  = json.loads(adf) if isinstance(adf, str) else adf

        ref_data = {}
        # Walk ADF nodes looking for table rows
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
                # Skip header row (first cell is "Customer Key") and note rows
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
    """
    Find a customer's reference record by fuzzy-matching the lowercase name
    against keys parsed from the Confluence reference page.
    """
    nl = name.lower()
    for key, rec in ref_data.items():
        if key and key in nl:
            return rec
    return {}

LOGO_PALETTE = [
    {"logo_color": "#0B1F45", "logo_bg": "#E6F1FB"},
    {"logo_color": "#0F5C8A", "logo_bg": "#E6F1FB"},
    {"logo_color": "#7B2FBE", "logo_bg": "#EEEDFE"},
    {"logo_color": "#0D6E85", "logo_bg": "#E1F5EE"},
    {"logo_color": "#854F0B", "logo_bg": "#FAEEDA"},
    {"logo_color": "#27500A", "logo_bg": "#EAF3DE"},
    {"logo_color": "#993556", "logo_bg": "#FBEAF0"},
    {"logo_color": "#1C3A6E", "logo_bg": "#E6F1FB"},
]

STATIC_OVERRIDES = {
    # ── page IDs sourced directly from Confluence — parent: 1990557712 ─────────
    "citizens": {
        "id": "citizens", "jql_keyword": "Citizens",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle", "MySQL", "PostgreSQL"],
        "portal_url": "https://citizens.tessell.com",
        "confluence_page_id": "2164948993"         # Citizens — Customer Dashboard
    },
    "atlas": {
        "id": "atlas-airlines", "jql_keyword": "Atlas Air",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165178370"         # Atlas Airlines — Customer Dashboard
    },
    "aon": {
        "id": "aon", "jql_keyword": "Aon",
        "cloud": "Azure", "region": "eastus",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165407755"         # AON — Customer Dashboard
    },
    "usda": {
        "id": "usda-exadata", "jql_keyword": "USDA",
        "cloud": "Azure", "region": "eastus",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165243927"         # USDA Exadata & Solaris/AIX — Customer Dashboard
    },
    "duncan": {
        "id": "duncan-solutions", "jql_keyword": "Duncan",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165866507"         # Duncan Solutions - Phase 2 — Customer Dashboard
    },
    "att": {
        "id": "att", "jql_keyword": "ATT",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165243947"         # ATT — Customer Dashboard
    },
    "boost": {
        "id": "boost-mobile", "jql_keyword": "Boost Mobile",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165800962"         # Boost Mobile — Customer Dashboard
    },
    "smfg": {
        "id": "smfg", "jql_keyword": "SMFG",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165538818"         # SMFG — Customer Dashboard
    },
    "pwc": {
        "id": "pwc-services", "jql_keyword": "PWC",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165604374"         # PWC - Services — Customer Dashboard
    },
    "advizex": {
        "id": "advizex-solutions", "jql_keyword": "Advizex",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165899266"         # Advizex Solutions — Customer Dashboard
    },
    "levis": {
        "id": "levis-phase-1", "jql_keyword": "Levis",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2164916227"         # Levis Phase-1 — Customer Dashboard
    },
    "williams": {
        "id": "williams", "jql_keyword": "Williams",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165243907"         # Williams — Customer Dashboard
    },
    "equinor": {
        "id": "equinor", "jql_keyword": "Equinor",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165604354"         # Equinor — Customer Dashboard
    },
    "brocacef": {
        "id": "brocacef-nl", "jql_keyword": "Brocacef",
        "cloud": "Azure", "region": "westeurope",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165309452"         # Brocacef-NL — Customer Dashboard
    },
    "magaya": {
        "id": "magaya", "jql_keyword": "Magaya",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2164719623"         # Magaya — Customer Dashboard
    },
    "darlingii": {
        "id": "darlingii", "jql_keyword": "Darlingii",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165932033"         # Darlingii — Customer Dashboard
    },
    "onity": {
        "id": "onity-group", "jql_keyword": "Onity",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165800982"         # Onity Group - Phase 1 — Customer Dashboard
    },
    "bhfl": {
        "id": "bhfl", "jql_keyword": "BHFL",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165964801"         # BHFL — Customer Dashboard
    },
    "collectors": {
        "id": "collectors", "jql_keyword": "Collectors",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165702658"         # Collectors — Customer Dashboard
    },
    "usss": {
        "id": "usss", "jql_keyword": "USSS",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165997569"         # USSS — Customer Dashboard
    },
    "landis": {
        "id": "landisgyr", "jql_keyword": "LandisGyr",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165768194"         # LandisGyr — Customer Dashboard
    },
    "sallie": {
        "id": "sallie-mae", "jql_keyword": "Sallie Mae",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165080066"         # Sallie Mae — Customer Dashboard
    },
}

def find_override(name):
    """Match customer name against STATIC_OVERRIDES — substring on lowercase."""
    nl = name.lower()
    for key, override in STATIC_OVERRIDES.items():
        if key in nl:
            return override
    return {}

# ── Normalise raw Jira displayNames to human-readable equivalents ──────────────
# Some accounts use username format (e.g. "siva.pradeep") instead of full names.
DISPLAY_NAME_MAP = {
    "siva.pradeep":        "Pradeep",
    "srivasram.devarajan": "Srivasram",
    "abdul.ali":           "Abdul",
    "Vinod K":             "Vinod",
    "Soumi Bose":          "Soumi",
    "Sajesh Rajagopal":    "Sajesh",
    "Uday Dhanikonda":     "Uday",
    "Ankush Jain":         "Ankush",
    "Jonathan Andrews":    "Jonathan",
}

def first_name(name):
    """
    Return first name only, Title Cased.
    Handles compound values like 'Kamal & Maneesh' by preserving the
    full string but capitalising each word — those are intentional combos.
    """
    if not name:
        return name
    # Compound names (contain &) — capitalise each word, keep full string
    if "&" in name:
        return " ".join(w.capitalize() for w in name.split())
    # Normal name — return first word only, Title Cased
    return name.split()[0].capitalize()

def normalise_display_name(raw):
    """Map raw Jira displayName → first name only."""
    if not raw:
        return "—"
    mapped = DISPLAY_NAME_MAP.get(raw, raw)
    return first_name(mapped)
# Populated once at startup by fetch_confluence_page_map()
_CONFLUENCE_PAGE_MAP = {}   # normalised customer name fragment → page_id

def fetch_confluence_page_map():
    """
    Fetch all child pages of CONFLUENCE_PARENT once per run.
    Builds a map of normalised title fragment → page_id so new customers
    get their Confluence page ID automatically without touching STATIC_OVERRIDES.
    e.g. "Citizens — Customer Dashboard" → key "citizens" → "2164948993"
    """
    global _CONFLUENCE_PAGE_MAP
    try:
        r = requests.get(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{CONFLUENCE_PARENT}/children",
            auth=conf_auth,
            headers={"Accept": "application/json"},
            params={"limit": 50}
        )
        if r.status_code != 200:
            print(f"  ⚠️  Could not fetch Confluence children: {r.status_code}")
            return
        pages = r.json().get("results", [])
        for p in pages:
            title = p.get("title", "")
            page_id = p.get("id", "")
            # Strip " — Customer Dashboard" suffix, lowercase, strip spaces
            name_part = title.replace("— Customer Dashboard", "").replace("- Customer Dashboard", "").strip().lower()
            # Store under the first word and full normalised name for flexible matching
            _CONFLUENCE_PAGE_MAP[name_part] = page_id
            first_word = name_part.split()[0] if name_part.split() else name_part
            _CONFLUENCE_PAGE_MAP[first_word] = page_id
        print(f"  📄 Confluence page map loaded — {len(pages)} pages under Customer Portfolio")
    except Exception as e:
        print(f"  ⚠️  Confluence page map fetch failed: {e}")

def lookup_confluence_page_id(customer_name):
    """
    Look up an existing Confluence page ID for a customer by name.
    Checks STATIC_OVERRIDES first, then falls back to the live page map.
    Returns "" if not found (script will then create a new page).
    """
    # 1. Static overrides win
    override = find_override(customer_name)
    if override.get("confluence_page_id"):
        return override["confluence_page_id"]
    # 2. Live Confluence page map
    nl = customer_name.lower()
    # Try progressively shorter matches
    for key, page_id in _CONFLUENCE_PAGE_MAP.items():
        if key and key in nl:
            return page_id
    return ""

# ── Description parser — extract cloud/region/engines/portal from epic text ───
def parse_epic_description(description):
    """
    Extract cloud, region, engines, and portal URL from free-text epic description.
    Falls back to sensible defaults when signals are absent.
    """
    if not description:
        return {}
    text = description.lower()

    # Cloud
    if "azure" in text:
        cloud = "Azure"
        region = "eastus"   # default Azure region
    else:
        cloud = "AWS"
        region = "us-east-1"   # default AWS region

    # Region hints — look for explicit region strings
    region_hints = {
        "us-east-1": "us-east-1", "us-east-2": "us-east-2",
        "us-west-1": "us-west-1", "us-west-2": "us-west-2",
        "eu-west-1": "eu-west-1", "eu-central-1": "eu-central-1",
        "ap-southeast-1": "ap-southeast-1", "ap-south-1": "ap-south-1",
        "eastus": "eastus", "westeurope": "westeurope",
        "centralus": "centralus", "southeastasia": "southeastasia",
    }
    for hint, val in region_hints.items():
        if hint in text:
            region = val
            break

    # Engines — scan for known engine names
    engines = []
    engine_map = [
        (["oracle"],                          "Oracle"),
        (["mysql"],                           "MySQL"),
        (["postgresql", "postgres"],          "PostgreSQL"),
        (["sql server", "mssql", "sqlserver"],"SQL Server"),
    ]
    for keywords, label in engine_map:
        if any(k in text for k in keywords):
            engines.append(label)
    if not engines:
        engines = ["Oracle"]   # default

    # Portal URL — look for tessell.com domain patterns
    portal_url = ""
    import re as _re
    portal_match = _re.search(r'https?://[\w.-]+\.tessell\.com[^\s\)\"\']*', description)
    if portal_match:
        portal_url = portal_match.group(0).rstrip(".,;")

    return {"cloud": cloud, "region": region, "engines": engines, "portal_url": portal_url}

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

def build_customer_entry(idx, name, status, owner, epic_key, description="", phase_override=None, ref_data=None):
    """
    Priority order for people fields:
      tam_primary   → CSO epic assignee.displayName (normalised)  [PRIMARY]
                    → ref tam_secondary from customer_reference.json  [FALLBACK if no assignee]
      tam_secondary → customer_reference.json only
      exec_sponsor  → customer_reference.json only
    SRE contact is intentionally excluded from all dashboard views.
    """
    ref_data     = ref_data or {}
    phase        = phase_override or status_to_phase(status)
    palette      = LOGO_PALETTE[idx % len(LOGO_PALETTE)]
    override     = find_override(name)
    parsed       = parse_epic_description(description)
    ref          = lookup_reference(name, ref_data)
    slug         = override.get("id") or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    conf_page_id = override.get("confluence_page_id") or lookup_confluence_page_id(name)

    # tam_primary: CSO assignee (normalised) is always primary;
    # fall back to ref tam_secondary only if epic has no assignee
    tam_primary   = normalise_display_name(owner) if owner else (ref.get("tam_secondary") or "—")
    tam_secondary = first_name(ref.get("tam_secondary", "") or "")
    exec_sponsor  = first_name(ref.get("exec_sponsor",  "") or "")

    # Avoid showing same name in both primary and secondary
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

# ── Build state helpers ────────────────────────────────────────────────────────
def load_build_state():
    """Load persisted per-customer fingerprints from last run."""
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
    """
    Lightweight dirtiness check — fetch only the 3 most-recently-updated
    SR/TS ticket keys + their updated timestamps for this customer.
    Returns a short hash string. Cost: 1 Jira API call per customer.
    """
    try:
        r = requests.get(
            f"{JIRA_BASE}/rest/api/3/search/jql",
            auth=auth, headers=headers,
            params={
                "jql": (f'project in (TS, SR) AND text ~ "{keyword}" '
                        f'AND updated >= -7d ORDER BY updated DESC'),
                "maxResults": 5,
                "fields": "updated,status,priority"
            }
        )
        if r.status_code != 200:
            return None   # can't determine — treat as dirty
        issues = r.json().get("issues", [])
        # fingerprint = hash of (key, updated, status, priority) tuples
        sig = "|".join(
            f"{i['key']}:{i['fields'].get('updated','')}:"
            f"{i['fields'].get('status',{}).get('name','')}:"
            f"{(i['fields'].get('priority') or {}).get('name','')}"
            for i in issues
        )
        return hashlib.md5(sig.encode()).hexdigest()
    except Exception:
        return None   # network error → treat as dirty

def is_dirty(cust_id, keyword, build_state):
    """Return True if this customer needs a rebuild."""
    if FORCE_REBUILD:
        return True
    fp = customer_fingerprint(keyword)
    if fp is None:
        return True   # unknown → rebuild to be safe
    return build_state.get(cust_id) != fp

def mark_clean(cust_id, keyword, build_state):
    fp = customer_fingerprint(keyword)
    if fp:
        build_state[cust_id] = fp

# ── Jira helpers ───────────────────────────────────────────────────────────────
def fetch_active_customers():
    # ── Load reference data and Confluence page map once ──────────────────────
    ref_data = load_customer_reference()
    print(f"  📋 Customer reference loaded — {len(ref_data)} entries")
    fetch_confluence_page_map()

    print("Tier 1: Fetching active implementation epics (CSO != Done)...")
    r1 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": "project = CSO AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC",
                "maxResults": 50, "fields": "summary,status,assignee,description,created,updated"}
    )
    r1.raise_for_status()
    tier1_epics = r1.json().get("issues", [])
    print(f"  Found {len(tier1_epics)} active implementation epics")

    print("Tier 2: Fetching completed epics with live TS/SR activity...")
    r2 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": "project = CSO AND issuetype = Epic AND statusCategory = Done ORDER BY updated DESC",
                "maxResults": 100, "fields": "summary,status,assignee,description,created,updated"}
    )
    r2.raise_for_status()
    done_epics = r2.json().get("issues", [])

    tier2_epics = []
    for epic in done_epics:
        name    = (epic["fields"].get("summary") or "").strip()
        override= find_override(name)
        keyword = override.get("jql_keyword", name)
        try:
            check = requests.get(
                f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": (f'project in (TS, SR) AND text ~ "{keyword}" '
                                f'AND statusCategory != Done AND updated >= -30d'),
                        "maxResults": 1, "fields": "summary"}
            )
            if check.status_code == 200 and check.json().get("total", 0) > 0:
                tier2_epics.append(epic)
        except Exception:
            pass

    def extract(epic):
        f = epic["fields"]
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
            customers.append(build_customer_entry(
                idx, name, status, owner, epic["key"], desc, ref_data=ref_data
            ))

    for epic in tier2_epics:
        name, _, owner, desc = extract(epic)
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            customers.append(build_customer_entry(
                len(customers), name, "Done", owner, epic["key"], desc,
                phase_override="Steady State", ref_data=ref_data
            ))

    print(f"\n  Total customers: {len(customers)}")
    return customers

def jql(query, max=20):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": query, "maxResults": max,
                "fields": "summary,priority,status,created,resolutiondate,issuetype,labels"}
    )
    r.raise_for_status()
    return r.json().get("issues", [])

def make_jqls(keyword):
    return {
        "p0p1":     (f'project in (TS, SR) AND text ~ "{keyword}" AND (labels = P0 OR labels = P1) AND statusCategory != Done ORDER BY created DESC'),
        "open":     (f'project in (TS, SR) AND text ~ "{keyword}" AND statusCategory != Done ORDER BY created DESC'),
        "features": (f'project in (TS, SR) AND text ~ "{keyword}" AND (issuetype in (Feature, "Feature Request", Story) OR labels in ("FeatureRequest", "Feature-Request")) AND statusCategory != Done ORDER BY created DESC'),
        "resolved": (f'project in (TS, SR) AND text ~ "{keyword}" AND statusCategory = Done AND resolutiondate >= -30d ORDER BY resolutiondate DESC'),
        "recent":   (f'project in (TS, SR) AND text ~ "{keyword}" AND updated >= -30d ORDER BY updated DESC'),
    }

def fetch_customer_data(keyword):
    queries = make_jqls(keyword)
    return {
        "p0p1":           jql(queries["p0p1"],     max=10),
        "open":           jql(queries["open"],     max=20),
        "features":       jql(queries["features"], max=10),
        "resolved":       jql(queries["resolved"], max=50),
        "recent":         jql(queries["recent"],   max=12),
        "ticket_history": fetch_monthly_buckets(keyword),
        "pulse":          fetch_pulse_from_comments(keyword),
    }

def fetch_monthly_buckets(keyword):
    from datetime import date
    buckets = []
    today = date.today()
    for i in range(5, -1, -1):
        month_offset = today.month - i
        year_offset  = today.year + (month_offset - 1) // 12
        month_num    = ((month_offset - 1) % 12) + 1
        first = date(year_offset, month_num, 1)
        last  = date(year_offset + 1, 1, 1) if month_num == 12 else date(year_offset, month_num + 1, 1)
        f_str, l_str = first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
        try:
            r_open = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": f'project = SR AND text ~ "{keyword}" AND created <= "{l_str}" AND (resolutiondate is EMPTY OR resolutiondate >= "{f_str}") ORDER BY created DESC',
                        "maxResults": 0, "fields": "summary"})
            open_count = r_open.json().get("total", 0) if r_open.status_code == 200 else 0
        except Exception:
            open_count = 0
        try:
            r_res = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": f'project = SR AND text ~ "{keyword}" AND statusCategory = Done AND resolutiondate >= "{f_str}" AND resolutiondate < "{l_str}" ORDER BY resolutiondate DESC',
                        "maxResults": 0, "fields": "summary"})
            resolved_count = r_res.json().get("total", 0) if r_res.status_code == 200 else 0
        except Exception:
            resolved_count = 0
        buckets.append({"month": first.strftime("%b %Y"), "count": open_count, "resolved": resolved_count})
    return buckets

def fetch_pulse_from_comments(keyword):
    try:
        r = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
            params={"jql": f'project = SR AND text ~ "{keyword}" AND updated >= -21d ORDER BY updated DESC',
                    "maxResults": 15, "fields": "summary,status,priority,labels,created,comment"})
        if r.status_code != 200: return []
        issues = r.json().get("issues", [])
        frustrated_kw = ["escalat","urgent","not working","still broken","days","week","unacceptable","blocking","critical","frustrated","disappointed","no progress","no update","no response","waiting","how long"]
        concerned_kw  = ["issue","problem","error","fail","broken","wrong","incorrect","unexpected","not expected","impact","affects","production"]
        positive_kw   = ["thank","resolved","fixed","working","great","smooth","appreciate","perfect","done","completed","success","good"]
        waiting_kw    = ["waiting","pending","any update","please update","eta","when","timeline","status update","follow up","followup"]
        pulse_items, seen = [], set()
        for issue in issues:
            f       = issue["fields"]
            summ    = (f.get("summary") or "")[:60]
            status  = (f.get("status", {}).get("name") or "").lower()
            labels  = [l.upper() for l in (f.get("labels") or [])]
            created = f.get("created", "")
            if ("P0" in labels or "P1" in labels) and "frustrated" not in seen:
                pulse_items.append({"sentiment":"frustrated","text":f"P{'0' if 'P0' in labels else '1'} open {age_days(created)} — {summ[:40]}"})
                seen.add("frustrated"); continue
            if any(x in status for x in ("pending","wait","hold")) and "waiting" not in seen:
                pulse_items.append({"sentiment":"waiting","text":f"Awaiting response — {summ[:45]}"})
                seen.add("waiting"); continue
            for c in reversed(f.get("comment", {}).get("comments", [])):
                if "tessell" in (c.get("author", {}).get("emailAddress") or "").lower(): continue
                body = c.get("body", {})
                text = ""
                if isinstance(body, dict):
                    for block in body.get("content", []):
                        for inline in block.get("content", []):
                            if inline.get("type") == "text": text += inline.get("text", "") + " "
                elif isinstance(body, str): text = body
                tl = text.lower()
                for kws, sent in [(frustrated_kw,"frustrated"),(waiting_kw,"waiting"),(positive_kw,"positive"),(concerned_kw,"concerned")]:
                    if any(k in tl for k in kws) and sent not in seen:
                        pulse_items.append({"sentiment":sent,"text":summ[:55]}); seen.add(sent); break
            if len(pulse_items) >= 5: break
        return pulse_items[:5]
    except Exception as e:
        print(f"  ⚠️  Pulse fetch failed: {e}"); return []

# ── Formatting helpers ─────────────────────────────────────────────────────────
def fmt_date(iso):
    if not iso: return "—"
    try:    return datetime.fromisoformat(iso[:10]).strftime("%b %d, %Y")
    except: return iso[:10]

def age_days(iso):
    if not iso: return "—"
    try:
        d = (datetime.now(timezone.utc) - datetime.fromisoformat(iso[:19]).replace(tzinfo=timezone.utc)).days
        return f"{d}d" if d > 0 else "today"
    except: return "—"

def sre_priority(fields):
    labels = [l.upper() for l in (fields.get("labels") or [])]
    if "P0" in labels: return "pc", "P0"
    if "P1" in labels: return "ph", "P1"
    return None, None

def priority_class(p):
    p = (p or "").lower()
    if p in ("highest","critical"): return "pc", "Highest"
    if p in ("high",):              return "ph", "High"
    if p in ("medium",):            return "pm", "Medium"
    return "pl", p.capitalize() or "—"

def status_class(s):
    s = (s or "").lower()
    if "progress" in s or "review" in s:                        return "si",  "In Progress"
    if "pending"  in s or "wait"   in s:                        return "spe", "Pending Eng"
    if "done"     in s or "closed" in s or "resolved" in s:     return "sc",  "Closed"
    return "so", s.capitalize() or "Open"

def ticket_row(issue):
    key  = issue["key"]
    f    = issue["fields"]
    summ = (f.get("summary") or "")[:72]
    sre_pc, sre_pl = sre_priority(f)
    pc, pl = (sre_pc, sre_pl) if sre_pc else priority_class(f.get("priority", {}).get("name", ""))
    sc_, sl = status_class(f.get("status", {}).get("name", ""))
    url  = f"{JIRA_BASE}/browse/{key}"
    return (f'<tr><td><a class="tlink" href="{url}" target="_blank">{key}</a></td>'
            f'<td>{summ}</td><td><span class="pb {pc}">{pl}</span></td>'
            f'<td><span class="sp {sc_}">{sl}</span></td><td>{age_days(f.get("created",""))}</td></tr>')

def compute_health(p0p1, open_tickets, features, resolved):
    score   = 10
    pending = len([i for i in open_tickets
                   if 'pending' in (i['fields'].get('status',{}).get('name','') or '').lower()])
    if   len(p0p1) >= 3:          score -= 4
    elif len(p0p1) == 2:          score -= 3
    elif len(p0p1) == 1:          score -= 2
    if   len(open_tickets) >= 10: score -= 2
    elif len(open_tickets) >= 6:  score -= 1
    if   pending >= 4:            score -= 2
    elif pending >= 2:            score -= 1
    if   len(features) >= 5:      score -= 1
    if   len(resolved) == 0:      score -= 1
    score = max(1, min(10, score))
    label = ("Healthy" if score >= 8 else "Stable" if score >= 6
             else "Needs Attention" if score >= 4 else "At Risk")
    color = "#68D391" if score >= 8 else "#FFC107" if score >= 6 else "#FC8181"
    hk    = ("healthy" if score >= 8 else "stable" if score >= 6
             else "attention" if score >= 4 else "atrisk")
    return score, label, color, hk, pending

# ── Timeline builder ───────────────────────────────────────────────────────────
def get_changelog(key):
    r = requests.get(f"{JIRA_BASE}/rest/api/3/issue/{key}/changelog",
                     auth=auth, headers=headers, params={"maxResults": 10})
    if r.status_code != 200: return []
    events = []
    for h in r.json().get("values", []):
        ts, author = h.get("created",""), h.get("author",{}).get("displayName","Tessell")
        for item in h.get("items", []):
            if item.get("field","") in ("status","priority"):
                events.append({"ts":ts,"key":key,"type":item["field"],
                                "from":item.get("fromString","") or "",
                                "to":item.get("toString","") or "","author":author})
    return events

def get_comments(key, max=2):
    r = requests.get(f"{JIRA_BASE}/rest/api/3/issue/{key}/comment",
                     auth=auth, headers=headers,
                     params={"maxResults":max,"orderBy":"-created"})
    if r.status_code != 200: return []
    out = []
    for c in r.json().get("comments", []):
        body = c.get("body", {})
        text = ""
        if isinstance(body, dict):
            for block in body.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text": text += inline.get("text","") + " "
        elif isinstance(body, str): text = body
        text = text.strip()[:120]
        if text:
            out.append({"ts":c.get("created",""),"key":key,"type":"comment",
                        "author":c.get("author",{}).get("displayName","Tessell"),"text":text})
    return out

def build_timeline(recent_issues, limit=8):
    all_events = []
    for issue in recent_issues[:12]:
        key  = issue["key"]
        summ = (issue["fields"].get("summary") or "")[:70]
        all_events.append({"ts":issue["fields"].get("created",""),"key":key,"type":"created","summary":summ})
        try:
            for ev in get_changelog(key): ev["summary"]=summ; all_events.append(ev)
        except: pass
        try:
            for ev in get_comments(key): ev["summary"]=summ; all_events.append(ev)
        except: pass

    def sk(e):
        try:    return datetime.fromisoformat(e["ts"][:19])
        except: return datetime.min
    all_events.sort(key=sk, reverse=True)

    seen, timeline = set(), []
    for ev in all_events:
        k,t    = ev["key"], ev["type"]
        ts_fmt = fmt_date(ev.get("ts",""))
        url    = f"{JIRA_BASE}/browse/{k}"
        summ   = ev.get("summary","")
        if t == "created" and k in seen: continue
        if t == "status":
            tl = ev["to"].lower()
            if any(x in tl for x in ("done","resolved","closed")):
                icon,bg,title,desc = "✅","#EAF3DE",f"{k} resolved — {summ}",f"Status → {ev['to']} by {ev['author']}"
            elif "progress" in tl:
                icon,bg,title,desc = "🔵","#E6F1FB",f"{k} moved to In Progress",f"{summ} — picked up by {ev['author']}"
            else:
                icon,bg,title,desc = "🔄","#F4F5F7",f"{k} status → {ev['to']}",f"{summ} — {ev['author']}"
        elif t == "priority":
            if ev["to"].lower() in ("p0","critical","highest"):
                icon,bg,title,desc = "🚨","#FFF5F5",f"{k} escalated to {ev['to']}",f"{summ} — raised by {ev['author']}"
            else:
                icon,bg,title,desc = "⚠️","#FFFAF0",f"{k} priority → {ev['to']}",f"{summ} — {ev['author']}"
        elif t == "comment":
            icon,bg,title,desc = "💬","#E6F1FB",f"Update on {k}",f"{ev['text']} — {ev['author']}"
        elif t == "created":
            icon,bg,title,desc = "🎫","#F4F5F7",f"{k} opened",summ
            seen.add(k)
        else: continue
        timeline.append(
            f'<div class="tl-item"><div class="tl-ic" style="background:{bg}">{icon}</div>'
            f'<div class="tl-content"><div class="tl-t"><a class="tlink" href="{url}" target="_blank">{k}</a> — {title}</div>'
            f'<div class="tl-d">{desc}</div><div class="tl-dt">{ts_fmt}</div></div></div>'
        )
        if len(timeline) >= limit: break
    return "\n".join(timeline) if timeline else \
           '<p style="padding:1rem;font-size:12px;color:#5E6C84">No recent activity found.</p>'

# ── Shared CSS ─────────────────────────────────────────────────────────────────
SHARED_CSS = """
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
body{background:#F4F5F7}
.nav{background:#0B1F45;padding:0 1.5rem;height:42px;display:flex;align-items:center;justify-content:space-between}
.nav-links{display:flex;gap:1.5rem}
.nl{font-size:12px;font-weight:500;color:rgba(255,255,255,0.45);text-decoration:none;padding-bottom:2px;border-bottom:2px solid transparent}
.nl.active{color:#fff;border-color:#00C2E0}
.nav-back{font-size:11px;color:#00C2E0;text-decoration:none}
.nav-status{display:flex;align-items:center;gap:5px;font-size:11px;color:#7DDBA3;background:rgba(125,219,163,0.12);padding:3px 10px;border-radius:20px;border:.5px solid rgba(125,219,163,0.25)}
.sdot{width:6px;height:6px;border-radius:50%;background:#7DDBA3}
.body{padding:1.25rem 1.5rem}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:1.25rem}
.metric{background:#fff;border-radius:8px;padding:.9rem 1rem;border:.5px solid #DFE1E6;cursor:pointer;transition:box-shadow .15s}
.metric:hover{box-shadow:0 0 0 2px #1A6FDB}
.metric.active{box-shadow:0 0 0 2px #1A6FDB;background:#F0F7FF}
.mlabel{font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}
.mval{font-size:24px;font-weight:700;line-height:1;margin-bottom:3px}
.msub{font-size:10px;color:#5E6C84}
.red{color:#E53E3E}.orange{color:#DD6B20}.yellow{color:#D69E2E}.green{color:#38A169}.blue{color:#1A6FDB}.gray{color:#5E6C84}
.grid2{display:grid;grid-template-columns:1fr 280px;gap:1rem;align-items:start}
.sec{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1rem}
.sec-head{padding:.7rem 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:center;gap:8px}
.sec-title{font-size:12px;font-weight:700;color:#172B4D}
.badge{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600}
.br{background:#FFF5F5;color:#A32D2D}.bo{background:#FFFAF0;color:#854F0B}.bb{background:#E6F1FB;color:#0C447C}.bg{background:#EAF3DE;color:#27500A}
table{width:100%;border-collapse:collapse;font-size:11px}
th{font-size:10px;font-weight:600;color:#5E6C84;padding:6px 1.1rem;text-align:left;background:#FAFBFC;border-bottom:.5px solid #DFE1E6;text-transform:uppercase;letter-spacing:.04em}
td{padding:7px 1.1rem;border-bottom:.5px solid #DFE1E6;color:#172B4D;vertical-align:middle}
tr:last-child td{border-bottom:none}
.tlink{color:#1A6FDB;text-decoration:none;font-weight:700;font-size:11px}
.pb{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px}
.pc{background:#E53E3E;color:#fff}.ph{background:#FFF5F5;color:#A32D2D}.pm{background:#FFFAF0;color:#854F0B}.pl{background:#F4F5F7;color:#5E6C84}
.sp{font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px}
.so{background:#FFF5F5;color:#A32D2D}.si{background:#E6F1FB;color:#0C447C}.spe{background:#FFFAF0;color:#854F0B}.sc{background:#EAF3DE;color:#27500A}
.ai-panel{background:#0B1F45;border-radius:10px;padding:1.1rem;margin-bottom:1rem}
.ai-eyebrow{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#00C2E0;margin-bottom:3px}
.ai-title{font-size:13px;font-weight:700;color:#fff;margin-bottom:8px}
.ai-body{font-size:11px;color:rgba(255,255,255,0.75);line-height:1.7}
.ai-footer{margin-top:8px;padding-top:8px;border-top:.5px solid rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:space-between}
.ai-score-label{font-size:10px;color:rgba(255,255,255,0.4)}
.ai-score-val{font-size:22px;font-weight:800}
.ai-score-max{font-size:11px;color:rgba(255,255,255,0.3)}
.ai-ts{font-size:10px;color:rgba(255,255,255,0.3)}
.sb-sec{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1rem}
.sb-head{padding:.7rem 1rem;border-bottom:.5px solid #DFE1E6;font-size:12px;font-weight:700;color:#172B4D}
.ir{display:flex;align-items:center;justify-content:space-between;padding:7px 1rem;border-bottom:.5px solid #DFE1E6}
.ir:last-child{border-bottom:none}
.ilabel{font-size:11px;color:#5E6C84}.ival{font-size:11px;font-weight:600;color:#172B4D}
.pulse-row{padding:7px 1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:flex-start;gap:7px}
.pulse-row:last-child{border-bottom:none}
.pdot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:3px}
.ptext{font-size:11px;color:#5E6C84;line-height:1.4}
.fr-item{padding:9px 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:flex-start;gap:8px}
.fr-item:last-child{border-bottom:none}
.fr-icon{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;margin-top:1px}
.fr-content{flex:1}
.fr-title{font-size:12px;font-weight:600;color:#172B4D;margin-bottom:2px}
.fr-meta{font-size:11px;color:#5E6C84}
.fr-status{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;flex-shrink:0;margin-top:2px}
.tl{padding:1rem 1.1rem}
.tl-item{display:flex;gap:10px;padding-bottom:1rem;position:relative}
.tl-item::before{content:'';position:absolute;left:13px;top:26px;bottom:0;width:1px;background:#DFE1E6}
.tl-item:last-child::before{display:none}
.tl-ic{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0;z-index:1}
.tl-content{flex:1}
.tl-t{font-size:11px;font-weight:700;color:#172B4D;margin-bottom:2px}
.tl-d{font-size:10px;color:#5E6C84;line-height:1.5}
.tl-dt{font-size:10px;color:#A0AEC0;margin-top:2px}
.drawer{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.25rem;display:none}
.drawer.open{display:block}
.drawer-head{padding:.7rem 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:center;justify-content:space-between}
.drawer-title{font-size:12px;font-weight:700;color:#172B4D}
.drawer-close{font-size:14px;color:#5E6C84;cursor:pointer;background:none;border:none;padding:0 4px;line-height:1}
"""

NAV_MASTER = """<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span><span class="nl active">Customers</span>
    <span class="nl">Incidents</span><span class="nl">Onboarding</span>
  </div>
</div>"""

NAV_CUSTOMER = """<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span><span class="nl active">Customers</span>
    <span class="nl">Incidents</span><span class="nl">Onboarding</span>
  </div>
  <a class="nav-back" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/{parent}" target="_parent">← All Customers</a>
</div>"""

HEALTH_JS = """
function runHealth(DATA) {
  const el=document.getElementById('ai-body'),sc=document.getElementById('ai-score');
  let score=10,findings=[],actions=[];
  if(DATA.p0p1>=3){score-=4;findings.push(`<b style="color:#FC8181">${DATA.p0p1} active P0 incidents</b> (${DATA.p0keys.join(', ')})`);actions.push(`Escalate ${DATA.p0keys[0]} to engineering leadership for same-day resolution`);}
  else if(DATA.p0p1===2){score-=3;findings.push(`<b style="color:#FC8181">2 active P0 incidents</b> (${DATA.p0keys.join(', ')})`);actions.push(`Both need an engineering owner today`);}
  else if(DATA.p0p1===1){score-=2;findings.push(`<b style="color:#FFC107">1 active P0/P1</b> (${DATA.p0keys[0]})`);actions.push(`Ensure ${DATA.p0keys[0]} has daily updates to customer`);}
  else{findings.push('<b style="color:#68D391">No active P0/P1 incidents</b>');}
  if(DATA.open>=8){score-=2;findings.push(`High backlog: <b>${DATA.open} tickets</b> open`);}
  else if(DATA.open>=5){score-=1;findings.push(`Moderate backlog: <b>${DATA.open} open tickets</b>`);}
  else{findings.push(`<b style="color:#68D391">Healthy ticket volume</b>: ${DATA.open} open`);}
  if(DATA.pendingEng>=4){score-=2;findings.push(`<b>${DATA.pendingEng} tickets stuck pending engineering</b>`);actions.push(`Set ETAs on all ${DATA.pendingEng} blocked tickets`);}
  else if(DATA.pendingEng>=2){score-=1;findings.push(`${DATA.pendingEng} tickets pending engineering`);}
  if(DATA.features>=5){score-=1;findings.push(`Large feature backlog: <b>${DATA.features} requests</b>`);actions.push('Schedule a feature roadmap call');}
  if(DATA.resolved===0){score-=1;findings.push('<b style="color:#FFC107">No tickets resolved in 30 days</b>');}
  else{findings.push(`<b style="color:#68D391">${DATA.resolved} resolved</b> in last 30 days`);}
  score=Math.max(1,Math.min(10,score));
  const color=score>=8?'#68D391':score>=6?'#FFC107':'#FC8181';
  const label=score>=8?'Healthy':score>=6?'Stable':score>=4?'Needs Attention':'At Risk';
  const badge=document.getElementById('health-badge'),dot=document.getElementById('health-dot');
  if(badge){badge.textContent=label;badge.style.color=color;}
  if(dot){dot.style.background=color;}
  if(badge&&badge.parentElement){badge.parentElement.style.borderColor=color+'4D';badge.parentElement.style.background=color+'1A';}
  let html=findings.map(f=>`<p style="margin-bottom:6px">• ${f}</p>`).join('');
  if(actions.length)html+=`<div style="margin-top:8px;padding-top:8px;border-top:.5px solid rgba(255,255,255,0.1)"><p style="font-size:10px;font-weight:700;color:#00C2E0;letter-spacing:.08em;text-transform:uppercase;margin-bottom:5px">Recommended Actions</p>${actions.map(a=>`<p style="margin-bottom:4px">→ ${a}</p>`).join('')}</div>`;
  el.innerHTML=html;sc.textContent=score;sc.style.color=color;
}
"""

# ── Customer dashboard builder ─────────────────────────────────────────────────
def build_customer_html(cust, data):
    now      = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    p0p1     = data["p0p1"]; open_t = data["open"]
    features = data["features"]; resolved = data["resolved"]
    timeline = build_timeline(data["recent"])
    score, health_label, health_color, _, pending = compute_health(p0p1, open_t, features, resolved)
    p0_keys  = [i["key"] for i in p0p1[:3]]
    high_keys= [i["key"] for i in open_t if (i['fields'].get('priority',{}).get('name','') or '').lower() in ('high','p1','highest')][:3]

    p0_rows = "".join(ticket_row(i) for i in p0p1[:5]) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No active P0/P1 incidents</td></tr>'
    tk_rows = "".join(ticket_row(i) for i in open_t[:10]) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No open tickets</td></tr>'

    feat_items = ""
    for i in features[:5]:
        key = i["key"]; summ = (i["fields"].get("summary") or "")[:65]; url = f"{JIRA_BASE}/browse/{key}"
        sc_, sl = status_class(i["fields"].get("status",{}).get("name",""))
        feat_items += (f'<div class="fr-item"><div class="fr-icon" style="background:#E6F1FB">💡</div>'
                       f'<div class="fr-content"><div class="fr-title">{summ}</div>'
                       f'<div class="fr-meta"><a class="tlink" href="{url}" target="_blank">{key}</a></div></div>'
                       f'<span class="fr-status {sc_}">{sl}</span></div>')

    portal_html = (f'<a href="{cust["portal_url"]}" target="_blank" style="color:#00C2E0;font-size:11px;text-decoration:none">{cust["portal_url"]}</a>') if cust.get("portal_url") else "—"
    engines_str = " · ".join(cust["engines"])

    # ── People fields ──────────────────────────────────────────────────────────
    tam_primary   = cust.get("tam_primary", "—")  or "—"
    tam_secondary = cust.get("tam_secondary", "")
    exec_sponsor  = cust.get("exec_sponsor", "—") or "—"
    tam_html = f'<div style="font-size:12px;font-weight:700;color:#172B4D">{tam_primary}</div>'
    if tam_secondary:
        tam_html += f'<div style="font-size:10px;color:#5E6C84;margin-top:1px">{tam_secondary} <span style="color:#DFE1E6">·</span> secondary</div>'
    hist = data.get("ticket_history", [])

    if hist:
        chart_labels      = json.dumps([h["month"][:6] for h in hist])
        chart_data        = json.dumps([h["count"] for h in hist])
        chart_max         = max(h["count"] for h in hist) + 2
        resolved_by_month = json.dumps([h.get("resolved", 0) for h in hist])
        timeseries_js = f"""
new Chart(document.getElementById('trendChart'),{{type:'bar',data:{{labels:{chart_labels},datasets:[
  {{label:'Open',data:{chart_data},backgroundColor:'rgba(26,111,219,0.85)',borderRadius:3,barPercentage:0.7,categoryPercentage:0.6}},
  {{label:'Resolved',data:{resolved_by_month},backgroundColor:'rgba(56,161,105,0.85)',borderRadius:3,barPercentage:0.7,categoryPercentage:0.6}}
]}},options:{{responsive:true,maintainAspectRatio:false,
  plugins:{{legend:{{display:true,position:'top',align:'end',labels:{{font:{{size:9}},color:'rgba(255,255,255,0.5)',boxWidth:8,padding:8}}}}}},
  scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:9}},color:'rgba(255,255,255,0.4)'}},border:{{display:false}}}},
           y:{{min:0,max:{chart_max},grid:{{color:'rgba(255,255,255,0.06)'}},ticks:{{font:{{size:9}},color:'rgba(255,255,255,0.4)',stepSize:2}},border:{{display:false}}}}}}}}}}); """
        chart_block = f'<div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Ticket Volume Trend</div><div style="position:relative;height:120px"><canvas id="trendChart"></canvas></div>'
    else:
        timeseries_js = ""; chart_block = '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding-top:1rem">No ticket history available.</div>'

    pulse_colors = {"frustrated":"#E53E3E","concerned":"#DD6B20","waiting":"#D69E2E","positive":"#38A169","neutral":"#5E6C84"}
    pulse_html = "".join(
        f'<div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px">'
        f'<div class="pdot" style="background:{pulse_colors.get(p["sentiment"],"#5E6C84")}"></div>'
        f'<div style="font-size:11px;color:rgba(255,255,255,0.7);line-height:1.4"><b style="color:#fff">{p["sentiment"].capitalize()}</b> — {p["text"]}</div></div>'
        for p in data.get("pulse", [])
    ) or '<div style="font-size:11px;color:rgba(255,255,255,0.3)">No pulse data yet.</div>'

    portal_link = (f'<div class="ir"><span class="ilabel">Portal</span><span class="ival"><a class="tlink" href="{cust["portal_url"]}" target="_blank">{cust["portal_url"]}</a></span></div>') if cust.get("portal_url") else ""
    kw_enc  = cust["jql_keyword"].replace(" ", "+").replace('"', '%22')
    ql_jira = f'{JIRA_BASE}/issues/?jql=text+~+%22{kw_enc}%22+AND+statusCategory+%21%3D+Done'

    data_js  = json.dumps({"p0p1":len(p0p1),"open":len(open_t),"features":len(features),"resolved":len(resolved),"pendingEng":pending,"p0keys":p0_keys,"highKeys":high_keys,"generated":now,"score":score,"scoreLabel":health_label,"scoreColor":health_color})
    mv_col   = "red"    if len(p0p1) > 0   else "green"
    open_col = "orange" if len(open_t) > 5 else "yellow"
    nav = NAV_CUSTOMER.format(parent=CONFLUENCE_PARENT)

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">
<title>{cust['name']} — Customer Dashboard</title>
<style>{SHARED_CSS}</style></head><body>
{nav}
<div style="background:#0B1F45;padding:1.1rem 1.5rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;border-bottom:1px solid #122752">
  <div style="display:flex;align-items:center;gap:10px">
    <div style="width:42px;height:42px;background:{cust['logo_bg']};border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:{cust['logo_color']}">{cust['initials']}</div>
    <div><div style="font-size:18px;font-weight:700;color:#fff">{cust['name']}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">{cust['cloud']} · {cust['region']} · {engines_str}</div></div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <div style="padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15)" id="health-wrap">
      <div style="width:7px;height:7px;border-radius:50%;background:{health_color}" id="health-dot"></div>
      <span id="health-badge" style="color:{health_color}">{health_label}</span>
    </div>
    <span style="font-size:10px;color:rgba(255,255,255,0.3)">Refreshed: {now}</span>
  </div>
</div>
<div class="body">
  <div style="background:#fff;border-radius:10px;border:.5px solid #DFE1E6;padding:.75rem 1.5rem;margin-bottom:1rem;display:grid;grid-template-columns:repeat(7,1fr);gap:1rem;align-items:start">
    <div><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">Account</div><div style="font-size:12px;font-weight:700;color:#172B4D">{cust['name']}</div></div>
    <div><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">Exec Sponsor</div><div style="font-size:12px;font-weight:700;color:#172B4D">{exec_sponsor}</div></div>
    <div style="grid-column:span 2"><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">TAM / TPM</div>{tam_html}</div>
    <div><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">Cloud</div><div style="font-size:12px;font-weight:700;color:#172B4D">{cust['cloud']} · {cust['region']}</div></div>
    <div><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">Phase</div><div style="font-size:12px;font-weight:700;color:#172B4D">{cust['phase']}</div></div>
    <div><div style="font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px">Portal</div><div>{portal_html}</div></div>
  </div>
  <div class="metrics">
    <div class="metric" id="m-p0p1" onclick="toggleDrawer('drawer-p0p1','m-p0p1')"><div class="mlabel">Open P0/P1</div><div class="mval {mv_col}">{len(p0p1)}</div><div class="msub">Active critical issues</div></div>
    <div class="metric" id="m-open" onclick="toggleDrawer('drawer-open','m-open')"><div class="mlabel">Open Tickets</div><div class="mval {open_col}">{len(open_t)}</div><div class="msub">Across all priorities</div></div>
    <div class="metric" id="m-feat" onclick="toggleDrawer('drawer-feat','m-feat')"><div class="mlabel">Feature Requests</div><div class="mval blue">{len(features)}</div><div class="msub">Pending delivery</div></div>
    <div class="metric" id="m-res" onclick="toggleDrawer('drawer-res','m-res')"><div class="mlabel">Resolved (30d)</div><div class="mval green">{len(resolved)}</div><div class="msub">Last 30 days</div></div>
    <div class="metric" id="m-health" onclick="toggleDrawer('drawer-health','m-health')"><div class="mlabel">Health Score (WIP)</div><div class="mval" style="color:{health_color}">{score}/10</div><div class="msub">Rule-based</div></div>
  </div>
  <div class="drawer" id="drawer-health">
    <div class="drawer-head"><span class="drawer-title">🧮 Health Score — {score}/10 · <span style="color:{health_color}">{health_label}</span></span><button class="drawer-close" onclick="toggleDrawer('drawer-health','m-health')">✕</button></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:.5px solid #DFE1E6">
      <div style="padding:1rem 1.25rem;border-right:.5px solid #DFE1E6"><div style="font-size:10px;font-weight:700;color:#5E6C84;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.75rem">Impacting Factors</div><div id="health-factors"></div></div>
      <div style="padding:1rem 1.25rem"><div style="font-size:10px;font-weight:700;color:#5E6C84;text-transform:uppercase;letter-spacing:.06em;margin-bottom:.75rem">How to Improve</div><div id="health-actions"></div></div>
    </div>
    <div style="padding:.75rem 1.25rem;background:#FAFBFC;display:flex;align-items:center;gap:6px">
      <div style="flex:1;height:8px;background:#F4F5F7;border-radius:4px;overflow:hidden"><div style="height:100%;border-radius:4px;background:{health_color};width:{score*10}%;transition:width .6s ease"></div></div>
      <span style="font-size:11px;font-weight:700;color:{health_color}">{score}/10</span>
      <span style="font-size:10px;color:#5E6C84">· Max deduction: {10-score} pts</span>
    </div>
  </div>
  <div class="drawer" id="drawer-p0p1"><div class="drawer-head"><span class="drawer-title">🚨 Open P0 / P1 Incidents ({len(p0p1)})</span><button class="drawer-close" onclick="toggleDrawer('drawer-p0p1','m-p0p1')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{p0_rows}</tbody></table></div>
  <div class="drawer" id="drawer-open"><div class="drawer-head"><span class="drawer-title">🎫 All Open Tickets ({len(open_t)})</span><button class="drawer-close" onclick="toggleDrawer('drawer-open','m-open')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{tk_rows}</tbody></table></div>
  <div class="drawer" id="drawer-feat"><div class="drawer-head"><span class="drawer-title">💡 Feature Requests ({len(features)})</span><button class="drawer-close" onclick="toggleDrawer('drawer-feat','m-feat')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{"".join(ticket_row(i) for i in features) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No feature requests</td></tr>'}</tbody></table></div>
  <div class="drawer" id="drawer-res"><div class="drawer-head"><span class="drawer-title">✅ Resolved Last 30 Days ({len(resolved)})</span><button class="drawer-close" onclick="toggleDrawer('drawer-res','m-res')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{"".join(ticket_row(i) for i in resolved) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No resolved tickets</td></tr>'}</tbody></table></div>
  <div class="grid2">
    <div>
      <div class="ai-panel">
        <div class="ai-eyebrow">✦ Health Analysis</div>
        <div class="ai-title">Customer Health Assessment</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;align-items:start">
          <div>
            <div class="ai-body" id="ai-body">Calculating...</div>
          </div>
          <div>{chart_block}</div>
          <div><div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Customer Pulse</div>{pulse_html}</div>
        </div>
      </div>
      <div class="sec"><div class="sec-head"><span class="sec-title">🚨 Active P0 / P1 Incidents</span><span class="badge br">{len(p0p1)} Open</span></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{p0_rows}</tbody></table></div>
      <div class="sec"><div class="sec-head"><span class="sec-title">🎫 Open Support Tickets</span><span class="badge bo">{len(open_t)} Open</span></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{tk_rows}</tbody></table></div>
      <div class="sec"><div class="sec-head"><span class="sec-title">💡 Feature Requests</span><span class="badge bb">{len(features)} Active</span></div>{feat_items or '<p style="padding:1rem;font-size:12px;color:#5E6C84">No open feature requests.</p>'}</div>
    </div>
    <div>
      <div class="sb-sec"><div class="sb-head">📅 Recent Activity</div><div class="tl">{timeline}</div></div>
      <div class="sb-sec"><div class="sb-head">🔗 Quick Links</div>
        <div class="ir"><a class="tlink" href="{ql_jira}" target="_blank">All Open Tickets</a></div>
        <div class="ir"><a class="tlink" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/{CONFLUENCE_PARENT}" target="_blank">Customer Portfolio</a></div>
        {portal_link}
      </div>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
{timeseries_js}
const DATA={data_js};
{HEALTH_JS}
window.onload=()=>{{runHealth(DATA);buildHealthDrawer(DATA);}};
function toggleDrawer(dId,mId){{const d=document.getElementById(dId),m=document.getElementById(mId),open=d.classList.contains('open');document.querySelectorAll('.drawer').forEach(x=>x.classList.remove('open'));document.querySelectorAll('.metric').forEach(x=>x.classList.remove('active'));if(!open){{d.classList.add('open');m.classList.add('active');}}}}
function buildHealthDrawer(DATA){{
  const factors=[],actions=[];
  if(DATA.p0p1>=3){{factors.push(['−4 pts',`${{DATA.p0p1}} active P0 incidents (${{DATA.p0keys.join(', ')}})`, '#E53E3E']);actions.push(['🚨','Escalate to engineering leadership']);}}
  else if(DATA.p0p1===2){{factors.push(['−3 pts',`2 P0 incidents (${{DATA.p0keys.join(', ')}})`, '#E53E3E']);actions.push(['🚨','Both need engineering owner today']);}}
  else if(DATA.p0p1===1){{factors.push(['−2 pts',`1 active P0/P1 (${{DATA.p0keys[0]}})`, '#DD6B20']);actions.push(['🚨','Daily updates to customer until resolved']);}}
  else{{factors.push(['+0 pts','No active P0/P1 incidents','#38A169']);}}
  if(DATA.open>=8){{factors.push(['−2 pts',`High backlog — ${{DATA.open}} open`,'#DD6B20']);actions.push(['🎫','Close or escalate stale tickets']);}}
  else if(DATA.open>=5){{factors.push(['−1 pt',`Moderate backlog — ${{DATA.open}} open`,'#D69E2E']);actions.push(['🎫','Target 3 resolutions this sprint']);}}
  else{{factors.push(['+0 pts',`Healthy volume — ${{DATA.open}} open`,'#38A169']);}}
  if(DATA.pendingEng>=4){{factors.push(['−2 pts',`${{DATA.pendingEng}} blocked pending eng`,'#DD6B20']);actions.push(['⏳','Set ETAs and communicate to customer']);}}
  else if(DATA.pendingEng>=2){{factors.push(['−1 pt',`${{DATA.pendingEng}} pending engineering`,'#D69E2E']);actions.push(['⏳','Chase ETAs this week']);}}
  else{{factors.push(['+0 pts','No tickets blocked on engineering','#38A169']);}}
  if(DATA.features>=5){{factors.push(['−1 pt',`${{DATA.features}} open feature requests`,'#D69E2E']);actions.push(['💡','Schedule roadmap call']);}}
  else{{factors.push(['+0 pts',`${{DATA.features}} feature requests`,'#38A169']);}}
  if(DATA.resolved===0){{factors.push(['−1 pt','No tickets resolved in 30d','#DD6B20']);actions.push(['✅','Close at least one ticket']);}}
  else{{factors.push(['+0 pts',`${{DATA.resolved}} resolved in 30d`,'#38A169']);}}
  document.getElementById('health-factors').innerHTML=factors.map(([pts,label,col])=>`<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:${{col}}1A;color:${{col}};flex-shrink:0;min-width:44px;text-align:center">${{pts}}</span><span style="font-size:11px;color:#172B4D;line-height:1.5">${{label}}</span></div>`).join('');
  const aEl=document.getElementById('health-actions');
  aEl.innerHTML=actions.length===0?'<p style="font-size:11px;color:#38A169;font-weight:600">✅ Customer is healthy!</p>':actions.map(([icon,text])=>`<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:13px;flex-shrink:0">${{icon}}</span><span style="font-size:11px;color:#172B4D;line-height:1.5">${{text}}</span></div>`).join('');
}}
</script></body></html>"""


# ── Master dashboard builder ───────────────────────────────────────────────────
def build_master_html(customer_results):
    now    = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    real   = [c for c in customer_results if c["config"].get("name")]
    total  = len(real)
    at_risk= sum(1 for c in real if c["health_key"]=="atrisk")
    healthy= sum(1 for c in real if c["health_key"] in ("healthy","stable"))
    total_p0 = sum(c["p0_count"] for c in real)

    cards = ""
    for cr in customer_results:
        cust = cr["config"]
        if not cust.get("name"): continue
        hk,hl,hcol = cr["health_key"],cr["health_label"],cr["health_color"]
        p0col = "red"    if cr["p0_count"]>0   else "green"
        tkcol = "orange" if cr["open_count"]>5 else "gray" if cr["open_count"]>2 else "green"
        tags  = "".join(f'<span class="tag">{e}</span>' for e in cust["engines"]) + f'<span class="tag">{cust["cloud"]}</span>'
        url   = cr.get("dashboard_url","#")
        phase_emoji = {"Onboarding":"🔵","Implementation":"🟡","Stabilisation":"🟠","Production":"🟢","Steady State":"⚫"}.get(cust["phase"],"")
        cards += f"""<a class="cust-card" data-health="{hk}" data-name="{cust['name'].lower()}" href="{url}" target="_parent" style="text-decoration:none;color:inherit">
  <div class="card-header">
    <div class="card-logo" style="background:{cust['logo_bg']};color:{cust['logo_color']}">{cust['initials']}</div>
    <div><div class="card-name">{cust['name']}</div><div class="card-meta">{cust['region']} · CSE: {cust.get('cse_owner','—')}</div></div>
    <div class="health-pill" style="background:{hcol}1A;border:1px solid {hcol}4D;color:{hcol}"><div class="hp-dot" style="background:{hcol}"></div>{hl}</div>
  </div>
  <div class="card-body">
    <div class="card-stats">
      <div class="cs"><div class="cs-val {p0col}">{cr['p0_count']}</div><div class="cs-label">P0/P1</div></div>
      <div class="cs"><div class="cs-val {tkcol}">{cr['open_count']}</div><div class="cs-label">Open</div></div>
      <div class="cs"><div class="cs-val blue">{cr['feat_count']}</div><div class="cs-label">Features</div></div>
    </div>
    <div class="card-tags">{tags}</div>
    <div class="card-footer"><span class="phase-lbl">{phase_emoji} {cust['phase']}</span><span class="drill-btn">View Dashboard →</span></div>
  </div>
</a>"""

    action_items = []
    for cr in sorted(customer_results, key=lambda x:x["p0_count"], reverse=True)[:3]:
        c   = cr["config"]
        url = cr.get("dashboard_url","#")
        if cr["p0_count"]>0:
            sev,sev_cls = "Critical","sev-critical"
            title = f"{c['name']} — {cr['p0_count']} P0{'s' if cr['p0_count']>1 else ''} open"
            desc  = f"{cr['open_count']} total open tickets. Immediate engineering escalation required."
        elif cr["open_count"]>5:
            sev,sev_cls = "High","sev-high"
            title = f"{c['name']} — {cr['open_count']} open tickets"
            desc  = f"{cr['feat_count']} feature requests pending."
        else:
            sev,sev_cls = "Watch","sev-watch"
            title = f"{c['name']} — monitor closely"
            desc  = f"Phase: {c['phase']}. {cr['open_count']} open tickets."
        action_items.append(f'<div class="action-item"><span class="ai-severity {sev_cls}">{sev}</span><div class="ai-title">{title}</div><div class="ai-desc">{desc}</div><a class="ai-link" href="{url}" target="_parent">→ View Dashboard</a></div>')
    while len(action_items)<3:
        action_items.append('<div class="action-item"><span class="ai-severity sev-watch">Watch</span><div class="ai-title">No further escalations</div><div class="ai-desc">Remaining customers are healthy.</div></div>')

    phase_counts = {"Onboarding":0,"Implementation":0,"Stabilisation":0,"Production":0,"Steady State":0}
    for cr in customer_results:
        p = cr["config"].get("phase","")
        if p in phase_counts: phase_counts[p]+=1
    pipe_max = max(phase_counts.values()) or 1
    def pipe_row(label,count,color,text_color):
        pct=round(count/pipe_max*100)
        return (f'<div class="phase-row"><span class="phase-label">{label}</span>'
                f'<div class="phase-track"><div class="phase-fill" style="width:{max(pct,8)}%;background:{color};color:{text_color}">{count if pct>15 else ""}</div></div>'
                f'<span class="phase-count" style="color:{color}">{count}</span></div>')
    pipeline_html = (pipe_row("Onboarding",phase_counts["Onboarding"],"#378ADD","#E6F1FB")+
                     pipe_row("Implementation",phase_counts["Implementation"],"#BA7517","#FAEEDA")+
                     pipe_row("Stabilisation",phase_counts["Stabilisation"],"#E24B4A","#FCEBEB")+
                     pipe_row("Production",phase_counts["Production"],"#1D9E75","#E1F5EE")+
                     pipe_row("Steady State",phase_counts["Steady State"],"#5F5E5A","#F1EFE8"))

    heatmap_cells = ""
    for cr in customer_results:
        c   = cr["config"]
        cls = {"atrisk":"hm-risk","attention":"hm-warn","stable":"hm-stable","healthy":"hm-good"}.get(cr["health_key"],"hm-stable")
        stat= f"{cr['p0_count']} P0s · {cr['open_count']} open" if cr["p0_count"]>0 else f"{cr['open_count']} open · {c['phase'][:12]}"
        url = cr.get("dashboard_url","#")
        heatmap_cells += f'<a class="hm-cell {cls}" href="{url}" target="_parent"><div class="hm-name">{c["name"][:18]}</div><div class="hm-stat">{stat}</div></a>'

    owner_map = {}
    for cr in customer_results:
        owner = cr["config"].get("exec_sponsor","—") or "—"
        if owner not in owner_map: owner_map[owner]={"p0":0,"open":0,"customers":[]}
        owner_map[owner]["p0"]+=cr["p0_count"]; owner_map[owner]["open"]+=cr["open_count"]
        owner_map[owner]["customers"].append(cr["config"]["name"].split()[0])
    avatar_colors=[{"bg":"#E6F1FB","col":"#0C447C"},{"bg":"#EEEDFE","col":"#3C3489"},{"bg":"#EAF3DE","col":"#27500A"},{"bg":"#FAEEDA","col":"#633806"},{"bg":"#FBEAF0","col":"#72243E"},{"bg":"#E1F5EE","col":"#085041"}]
    owner_rows=""
    for idx,(owner,d) in enumerate(sorted(owner_map.items(),key=lambda x:-x[1]["p0"])[:5]):
        ac=avatar_colors[idx%len(avatar_colors)]; parts=owner.split()
        initials=(parts[0][0]+(parts[1][0] if len(parts)>1 else parts[0][-1])).upper() if parts else "—"
        custs=", ".join(d["customers"][:3])+("…" if len(d["customers"])>3 else "")
        p0col="#E53E3E" if d["p0"]>0 else "#D69E2E"; tkcol="#DD6B20" if d["open"]>5 else "#D69E2E" if d["open"]>2 else "#38A169"
        owner_rows+=(f'<div class="owner-row"><div class="owner-info"><div class="owner-avatar" style="background:{ac["bg"]};color:{ac["col"]}">{initials}</div>'
                     f'<div><div class="owner-name">{owner}</div><div class="owner-meta">{custs}</div></div></div>'
                     f'<div class="owner-counts"><div class="oc"><div class="oc-val" style="color:{p0col}">{d["p0"]}</div><div class="oc-label">P0s</div></div>'
                     f'<div class="oc"><div class="oc-val" style="color:{tkcol}">{d["open"]}</div><div class="oc-label">Open</div></div></div></div>')

    top5 = sorted([cr for cr in customer_results if cr["open_count"]>0],key=lambda x:-x["open_count"])[:5]
    trend_max = top5[0]["open_count"] if top5 else 1
    trend_rows="".join(
        f'<div class="trend-row"><span class="trend-label">{cr["config"]["name"].split()[0][:10]}</span>'
        f'<div class="trend-bar-wrap"><div class="trend-bar" style="width:{round(cr["open_count"]/trend_max*100)}%;background:{"#E53E3E" if cr["p0_count"]>0 else "#DD6B20" if cr["open_count"]>5 else "#38A169"}"></div></div>'
        f'<span class="trend-val" style="color:{"#E53E3E" if cr["p0_count"]>0 else "#DD6B20" if cr["open_count"]>5 else "#38A169"}">{cr["open_count"]}</span></div>'
        for cr in top5)

    highlights=[]
    crit=[cr for cr in customer_results if cr["p0_count"]>0]
    if crit: highlights.append(f'🚨 <span style="color:#172B4D;font-weight:600">{sum(c["p0_count"] for c in crit)} P0/P1s open</span> — {", ".join(c["config"]["name"].split()[0] for c in crit[:2])} need immediate attention')
    new_impl=[cr for cr in customer_results if cr["config"].get("phase") in ("Onboarding","Implementation")]
    if new_impl: highlights.append(f'🔄 <span style="color:#172B4D;font-weight:600">{len(new_impl)} customers</span> actively in implementation')
    prod=[cr for cr in customer_results if cr["config"].get("phase")=="Production"]
    if prod: highlights.append(f'✅ <span style="color:#172B4D;font-weight:600">{len(prod)} customers</span> in Production phase')
    highlights.append(f'📋 <span style="color:#172B4D;font-weight:600">{total} total customers</span> — {healthy} healthy, {at_risk} at risk')
    highlights_html="".join(f'<div style="font-size:11px;color:#5E6C84;line-height:1.7;border-bottom:.5px solid #F4F5F7;padding-bottom:.6rem;margin-bottom:.6rem">{h}</div>' for h in highlights[:4])

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">
<title>CSE — Customer Portfolio</title>
<style>
{SHARED_CSS}
.wordmark-bar{{width:3px;height:36px;background:#00C2E0;border-radius:2px;flex-shrink:0}}
.hero{{background:#0B1F45;padding:1.5rem 1.5rem 1.75rem}}
.hero-top{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:1.25rem;flex-wrap:wrap;gap:8px}}
.kpi-strip{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}}
.kpi{{background:rgba(255,255,255,0.06);border:.5px solid rgba(255,255,255,0.1);border-radius:10px;padding:1rem 1.1rem;position:relative;overflow:hidden}}
.kpi-label{{font-size:10px;font-weight:500;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}}
.kpi-val{{font-size:28px;font-weight:700;color:#fff;line-height:1}}
.kpi-sub{{font-size:10px;margin-top:4px}}
.kpi-accent{{position:absolute;top:0;left:0;width:3px;height:100%}}
.action-strip{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;margin-bottom:1.25rem;overflow:hidden}}
.action-head{{background:#0B1F45;padding:.75rem 1.25rem;display:flex;align-items:center;justify-content:space-between}}
.action-head-title{{font-size:12px;font-weight:700;color:#fff;display:flex;align-items:center;gap:8px}}
.action-head-badge{{font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(252,129,129,0.2);color:#FC8181;border:.5px solid rgba(252,129,129,0.3)}}
.action-head-ts{{font-size:10px;color:rgba(255,255,255,0.3)}}
.action-items{{display:grid;grid-template-columns:repeat(3,1fr)}}
.action-item{{padding:.9rem 1.25rem;border-right:.5px solid #F4F5F7}}
.action-item:last-child{{border-right:none}}
.ai-severity{{font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;display:inline-block;margin-bottom:6px}}
.sev-critical{{background:#FFF5F5;color:#A32D2D}}.sev-high{{background:#FFFAF0;color:#854F0B}}.sev-watch{{background:#E6F1FB;color:#0C447C}}
.ai-title{{font-size:12px;font-weight:700;color:#172B4D;margin-bottom:3px;line-height:1.35}}
.ai-desc{{font-size:11px;color:#5E6C84;line-height:1.5}}
.ai-link{{font-size:11px;font-weight:600;color:#1A6FDB;margin-top:5px;display:block;text-decoration:none}}
.main-grid{{display:grid;grid-template-columns:1fr 1fr 300px;gap:1.1rem;align-items:start}}
.pipeline{{padding:.9rem 1.1rem}}
.phase-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.phase-row:last-child{{margin-bottom:0}}
.phase-label{{font-size:11px;color:#5E6C84;width:110px;flex-shrink:0}}
.phase-track{{flex:1;height:20px;background:#F4F5F7;border-radius:4px;overflow:hidden}}
.phase-fill{{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:10px;font-weight:700;min-width:8px}}
.phase-count{{font-size:11px;font-weight:700;width:20px;text-align:right;flex-shrink:0}}
.heatmap{{padding:.9rem 1.1rem;display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}
.hm-cell{{border-radius:6px;padding:7px 8px;display:block;text-decoration:none;transition:filter .15s}}
.hm-cell:hover{{filter:brightness(0.93)}}
.hm-name{{font-size:10px;font-weight:600;line-height:1.3;margin-bottom:2px}}
.hm-stat{{font-size:10px;opacity:.75}}
.hm-risk{{background:#FFF5F5;border:.5px solid #F09595}}.hm-risk .hm-name,.hm-risk .hm-stat{{color:#A32D2D}}
.hm-warn{{background:#FFFAF0;border:.5px solid #EF9F27}}.hm-warn .hm-name,.hm-warn .hm-stat{{color:#854F0B}}
.hm-stable{{background:#E6F1FB;border:.5px solid #85B7EB}}.hm-stable .hm-name,.hm-stable .hm-stat{{color:#0C447C}}
.hm-good{{background:#EAF3DE;border:.5px solid #97C459}}.hm-good .hm-name,.hm-good .hm-stat{{color:#27500A}}
.sb-sec{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.1rem}}
.sb-head{{padding:.7rem 1rem;border-bottom:.5px solid #DFE1E6;font-size:12px;font-weight:700;color:#172B4D}}
.owner-row{{display:flex;align-items:center;justify-content:space-between;padding:7px 1rem;border-bottom:.5px solid #DFE1E6}}
.owner-row:last-child{{border-bottom:none}}
.owner-info{{display:flex;align-items:center;gap:8px}}
.owner-avatar{{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}}
.owner-name{{font-size:12px;font-weight:600;color:#172B4D}}.owner-meta{{font-size:10px;color:#5E6C84}}
.owner-counts{{display:flex;gap:8px}}.oc{{text-align:center}}
.oc-val{{font-size:13px;font-weight:700}}.oc-label{{font-size:9px;color:#5E6C84}}
.trend-row{{display:flex;align-items:center;gap:8px;padding:6px 1rem;border-bottom:.5px solid #DFE1E6}}
.trend-row:last-child{{border-bottom:none}}
.trend-label{{font-size:11px;color:#5E6C84;width:60px;flex-shrink:0}}
.trend-bar-wrap{{flex:1;height:6px;background:#F4F5F7;border-radius:3px;overflow:hidden}}
.trend-bar{{height:100%;border-radius:3px}}
.trend-val{{font-size:11px;font-weight:700;width:20px;text-align:right;flex-shrink:0}}
.cards-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:1.1rem}}
.cust-card{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;transition:transform .15s;display:block}}
.cust-card:hover{{transform:translateY(-2px)}}
.card-header{{padding:.9rem 1rem .75rem;border-bottom:.5px solid #F4F5F7;display:flex;align-items:center;gap:10px}}
.card-logo{{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0}}
.card-name{{font-size:12px;font-weight:700;color:#172B4D;margin-bottom:1px}}.card-meta{{font-size:10px;color:#5E6C84}}
.health-pill{{margin-left:auto;padding:3px 8px;border-radius:20px;font-size:10px;font-weight:700;display:flex;align-items:center;gap:4px;flex-shrink:0}}
.hp-dot{{width:6px;height:6px;border-radius:50%}}
.card-body{{padding:.75rem 1rem}}
.card-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:.7rem}}
.cs{{text-align:center}}.cs-val{{font-size:17px;font-weight:700;line-height:1}}.cs-label{{font-size:10px;color:#5E6C84;margin-top:2px}}
.card-tags{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:.7rem}}
.tag{{font-size:10px;padding:2px 6px;border-radius:4px;background:#F4F5F7;color:#5E6C84;font-weight:500}}
.card-footer{{display:flex;align-items:center;justify-content:space-between;padding-top:.6rem;border-top:.5px solid #F4F5F7}}
.phase-lbl{{font-size:10px;font-weight:600;color:#5E6C84}}.drill-btn{{font-size:11px;font-weight:600;color:#1A6FDB}}
.sec-divider{{font-size:13px;font-weight:700;color:#172B4D;margin:1.25rem 0 .75rem;display:flex;align-items:center;gap:8px}}
.sec-divider::after{{content:'';flex:1;height:.5px;background:#DFE1E6}}
.filter-bar{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.filter-btn{{font-size:11px;font-weight:500;padding:4px 12px;border-radius:20px;border:.5px solid #DFE1E6;background:#fff;color:#5E6C84;cursor:pointer}}
.filter-btn.active{{background:#0B1F45;color:#fff;border-color:#0B1F45}}
.search-input{{flex:1;max-width:220px;padding:5px 12px;border-radius:20px;border:.5px solid #DFE1E6;font-size:12px;outline:none;background:#fff;color:#172B4D}}
</style></head><body>
{NAV_MASTER}
<div class="hero">
  <div class="hero-top">
    <div style="display:flex;align-items:center;gap:10px">
      <div class="wordmark-bar"></div>
      <div><div style="font-size:20px;font-weight:700;color:#fff">Customer Success Portfolio</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:2px">Executive overview · Tessell CSE · Auto-refreshed from Jira every 30 minutes</div></div>
    </div>
    <div style="text-align:right">
      <div style="font-size:12px;font-weight:500;color:rgba(255,255,255,0.55)">{datetime.now(timezone.utc).strftime("%B %d, %Y")}</div>
      <div style="font-size:10px;color:rgba(255,255,255,0.3);margin-top:2px">{now}</div>
    </div>
  </div>
  <div class="kpi-strip">
    <div class="kpi"><div class="kpi-accent" style="background:#00C2E0"></div><div class="kpi-label">Total customers</div><div class="kpi-val">{total}</div><div class="kpi-sub" style="color:rgba(255,255,255,0.4)">Active accounts</div></div>
    <div class="kpi"><div class="kpi-accent" style="background:#FC8181"></div><div class="kpi-label">At risk</div><div class="kpi-val" style="color:#FC8181">{at_risk}</div><div class="kpi-sub" style="color:#FC8181">Needs immediate action</div></div>
    <div class="kpi"><div class="kpi-accent" style="background:#FC8181"></div><div class="kpi-label">Open P0 / P1</div><div class="kpi-val" style="color:#FC8181">{total_p0}</div><div class="kpi-sub" style="color:rgba(255,255,255,0.4)">Across all customers</div></div>
    <div class="kpi"><div class="kpi-accent" style="background:#FFC107"></div><div class="kpi-label">In implementation</div><div class="kpi-val" style="color:#FFC107">{phase_counts['Onboarding']+phase_counts['Implementation']}</div><div class="kpi-sub" style="color:rgba(255,255,255,0.4)">Active onboarding</div></div>
    <div class="kpi"><div class="kpi-accent" style="background:#68D391"></div><div class="kpi-label">Healthy</div><div class="kpi-val" style="color:#68D391">{healthy}</div><div class="kpi-sub" style="color:rgba(255,255,255,0.4)">Stable, no escalations</div></div>
  </div>
</div>
<div class="body">
  <div class="action-strip">
    <div class="action-head">
      <div class="action-head-title"><span style="font-size:14px">🔴</span> Action Required
        <span class="action-head-badge">{min(3,len([cr for cr in customer_results if cr['p0_count']>0 or cr['open_count']>5]))} items</span>
      </div>
    </div>
    <div class="action-items">{''.join(action_items)}</div>
  </div>
  <div class="main-grid">
    <div>
      <div class="sec"><div class="sec-head"><span class="sec-title">Implementation pipeline</span><span style="font-size:10px;color:#5E6C84">{total} total</span></div><div class="pipeline">{pipeline_html}</div></div>
      <div class="sec"><div class="sec-head"><span class="sec-title">Open ticket load by customer</span><span style="font-size:10px;color:#5E6C84">Top 5</span></div><div style="padding:6px 0 4px">{trend_rows}</div></div>
    </div>
    <div><div class="sec"><div class="sec-head"><span class="sec-title">Customer health heatmap</span><span style="font-size:10px;color:#5E6C84">Click any cell to drill in</span></div><div class="heatmap">{heatmap_cells}</div></div></div>
    <div>
      <div class="sb-sec"><div class="sb-head">CSE ownership summary</div>{owner_rows}</div>
      <div class="sb-sec"><div class="sb-head">This week's highlights</div><div style="padding:.75rem 1rem">{highlights_html}</div></div>
    </div>
  </div>
  <div class="sec-divider">All Customers
    <div class="filter-bar" style="margin:0">
      <button class="filter-btn active" onclick="filterCards('all',this)">All</button>
      <button class="filter-btn" onclick="filterCards('atrisk',this)">At Risk</button>
      <button class="filter-btn" onclick="filterCards('attention',this)">Needs Attention</button>
      <button class="filter-btn" onclick="filterCards('healthy',this)">Healthy</button>
      <button class="filter-btn" onclick="filterCards('stable',this)">Stable</button>
      <input class="search-input" type="text" placeholder="Search..." oninput="searchCards(this.value)"/>
    </div>
  </div>
  <div class="cards-grid">{cards}</div>
</div>
<script>
function filterCards(h,btn){{document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.cust-card').forEach(el=>{{el.style.display=h==='all'||el.dataset.health===h?'':'none';}});}}
function searchCards(q){{q=q.toLowerCase();document.querySelectorAll('.cust-card').forEach(el=>{{el.style.display=(el.dataset.name||'').includes(q)?'':'none';}});}}
</script></body></html>"""


# ── Confluence helpers ─────────────────────────────────────────────────────────
def get_confluence_page_version(page_id):
    r = requests.get(f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{page_id}",
                     auth=conf_auth, headers={"Accept":"application/json"})
    return r.json().get("version",{}).get("number",1) if r.status_code==200 else 1

def confluence_page_url(page_id):
    """Canonical Confluence page URL — the ONLY link ever shown to users."""
    if not page_id:
        return "#"
    return f"https://tessell.atlassian.net/wiki/spaces/CSE/pages/{page_id}"

def ensure_confluence_page(cust, dashboard_url):
    page_id    = cust.get("confluence_page_id","").strip()
    busted_url = f"{dashboard_url}?v={CACHE_BUST}"  # GitHub URL only used as iframe src, never as a nav link
    iframe_body = json.dumps({"version":1,"type":"doc","content":[{"type":"extension","attrs":{
        "extensionType":"com.atlassian.confluence.macro.core","extensionKey":"iframe",
        "parameters":{"macroParams":{"src":{"value":busted_url},"width":{"value":"100%"},"height":{"value":"900px"},"frameborder":{"value":"0"},"scrolling":{"value":"yes"}}},
        "layout":"full-width"}}]})
    if page_id:
        ver = get_confluence_page_version(page_id)
        r   = requests.put(f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{page_id}",
                           auth=conf_auth, headers=conf_headers,
                           json={"id":page_id,"status":"current","title":f"{cust['name']} — Customer Dashboard",
                                 "version":{"number":ver+1},"body":{"representation":"atlas_doc_format","value":iframe_body}})
        if r.status_code in (200,204): print(f"  ✅ Updated Confluence page {page_id} (v{ver+1})")
        else: print(f"  ⚠️  Could not update {page_id}: {r.status_code} {r.text[:120]}")
        return page_id
    else:
        r = requests.post(f"{CONFLUENCE_BASE}/wiki/api/v2/pages",
                          auth=conf_auth, headers=conf_headers,
                          json={"spaceId":CONFLUENCE_SPACE,"parentId":CONFLUENCE_PARENT,"status":"current",
                                "title":f"{cust['name']} — Customer Dashboard",
                                "body":{"representation":"atlas_doc_format","value":iframe_body}})
        if r.status_code==200:
            new_id=r.json()["id"]; cust["confluence_page_id"]=new_id
            print(f"  ✅ Created Confluence page {new_id} for {cust['name']}"); return new_id
        else:
            print(f"  ⚠️  Could not create page for {cust['name']}: {r.status_code} {r.text[:200]}"); return ""


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    build_state = load_build_state()
    print(f"  Build state loaded — {len(build_state)} customers have prior fingerprints")
    if FORCE_REBUILD:
        print("  ⚠️  FORCE_REBUILD=1 — all customer pages will be rebuilt")

    CUSTOMERS = fetch_active_customers()
    with open("customers.json","w") as f: json.dump(CUSTOMERS,f,indent=2)
    print(f"  Saved {len(CUSTOMERS)} customers to customers.json")

    customer_results = []
    pages_updated    = False
    rebuilt          = []
    skipped          = []

    for cust in CUSTOMERS:
        cust_id = cust["id"]
        keyword = cust["jql_keyword"]

        # ── Check for existing HTML (need summary stats even for skipped customers) ─
        filename = f"{cust_id}_dashboard.html"
        gh_url   = f"https://vinod-tessell.github.io/cse-confluence/{filename}"
        conf_url = confluence_page_url(cust.get("confluence_page_id",""))

        # ── Skipped customers: resolve conf_url from stored page_id ──────────────
        conf_url = confluence_page_url(cust.get("confluence_page_id",""))
        if not is_dirty(cust_id, keyword, build_state) and os.path.exists(filename):
            # ── SKIP: load lightweight summary from existing build_state metadata ──
            cached = build_state.get(f"{cust_id}__meta", {})
            print(f"  ⏭  {cust['name']} — unchanged, skipping rebuild")
            skipped.append(cust["name"])
            customer_results.append({
                "config":      cust,
                "health_key":  cached.get("health_key","stable"),
                "health_label":cached.get("health_label","Stable"),
                "health_color":cached.get("health_color","#FFC107"),
                "p0_count":    cached.get("p0_count",0),
                "open_count":  cached.get("open_count",0),
                "feat_count":  cached.get("feat_count",0),
                "dashboard_url": conf_url,
            })
            continue

        # ── DIRTY: full rebuild ────────────────────────────────────────────────
        print(f"\n── {cust['name']} ({cust['cso_epic']} · {cust['cso_status']}) ──")
        print(f"  Fetching Jira data (keyword: {keyword})...")
        try:
            data = fetch_customer_data(keyword)
        except Exception as e:
            print(f"  ⚠️  Jira fetch failed: {e}")
            customer_results.append({
                "config":cust,"health_key":"stable","health_label":"Unknown",
                "health_color":"#5E6C84","p0_count":0,"open_count":0,
                "feat_count":0,"dashboard_url":conf_url
            })
            continue

        print(f"  P0/P1:{len(data['p0p1'])}  Open:{len(data['open'])}  Features:{len(data['features'])}  Resolved(30d):{len(data['resolved'])}")
        score, label, color, hk, pending = compute_health(data["p0p1"],data["open"],data["features"],data["resolved"])

        html = build_customer_html(cust, data)
        with open(filename,"w") as f: f.write(html)
        print(f"  ✅ Written {filename}")

        page_id = ensure_confluence_page(cust, gh_url)
        if page_id and page_id != cust.get("confluence_page_id",""):
            cust["confluence_page_id"] = page_id; pages_updated = True

        # ── All nav links point to Confluence only — GitHub URL is iframe-internal ──
        # Re-read page_id from cust after ensure_confluence_page may have written it back
        conf_url = confluence_page_url(cust.get("confluence_page_id", ""))

        result = {
            "config":cust,"health_key":hk,"health_label":label,"health_color":color,
            "p0_count":len(data["p0p1"]),"open_count":len(data["open"]),
            "feat_count":len(data["features"]),"dashboard_url":conf_url,
        }
        customer_results.append(result)
        rebuilt.append(cust["name"])

        # ── Persist fingerprint + lightweight meta for next run ────────────────
        mark_clean(cust_id, keyword, build_state)
        build_state[f"{cust_id}__meta"] = {
            "health_key":hk,"health_label":label,"health_color":color,
            "p0_count":len(data["p0p1"]),"open_count":len(data["open"]),"feat_count":len(data["features"])
        }
        save_build_state(build_state)   # save incrementally — crash-safe

    if pages_updated:
        with open("customers.json","w") as f: json.dump(CUSTOMERS,f,indent=2)
        print("\n✅ customers.json updated with new Confluence page IDs")

    print(f"\n── Build summary: {len(rebuilt)} rebuilt, {len(skipped)} skipped ──")
    if rebuilt: print(f"  Rebuilt:  {', '.join(rebuilt)}")
    if skipped: print(f"  Skipped:  {', '.join(skipped)}")

    # ── Master dashboard — always rebuilt (fast, no Jira calls) ───────────────
    print("\n── Master Dashboard (always rebuilt) ───────────────────────────")
    master = build_master_html(customer_results)
    with open("master_dashboard.html","w") as f: f.write(master)
    print("✅ master_dashboard.html written")

    master_page_id = os.environ.get("MASTER_CONFLUENCE_PAGE_ID","").strip()
    if master_page_id:
        master_gh_url = f"https://vinod-tessell.github.io/cse-confluence/master_dashboard.html"
        ensure_confluence_page({"name":"CSE Portfolio","confluence_page_id":master_page_id}, master_gh_url)

    print("\nAll done!")
