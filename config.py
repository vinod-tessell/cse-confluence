"""
config.py — environment variables, auth objects, and shared constants.
All other modules import from here; nothing imports from them.
"""
import os
from datetime import datetime, timezone, timedelta
from requests.auth import HTTPBasicAuth

# ── Jira ──────────────────────────────────────────────────────────────────────
JIRA_BASE  = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_API_TOKEN"]

# ── Confluence ────────────────────────────────────────────────────────────────
CONFLUENCE_BASE   = os.environ.get("CONFLUENCE_BASE_URL",   JIRA_BASE)
CONFLUENCE_EMAIL  = os.environ.get("CONFLUENCE_EMAIL",      JIRA_EMAIL)
CONFLUENCE_TOKEN  = os.environ.get("CONFLUENCE_API_TOKEN",  JIRA_TOKEN)
CONFLUENCE_SPACE  = os.environ.get("CONFLUENCE_SPACE_ID",   "1225719811")
CONFLUENCE_PARENT = os.environ.get("CONFLUENCE_PARENT_ID",  "1990557712")

# Customer Reference Data page (TAM secondary / exec sponsor table)
REFERENCE_PAGE_ID = "2166030367"

# ── Auth + headers ────────────────────────────────────────────────────────────
auth         = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
conf_auth    = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN)
headers      = {"Accept": "application/json"}
conf_headers = {"Accept": "application/json", "Content-Type": "application/json"}

# ── Timezone / build flags ────────────────────────────────────────────────────
EST            = timezone(timedelta(hours=-5), 'EST')
FORCE_REBUILD  = os.environ.get("FORCE_REBUILD", "0") == "1"
BUILD_STATE_FILE = "build_state.json"
CACHE_BUST     = int(datetime.now(EST).timestamp())

# ── Visual palette — cycled by customer index ─────────────────────────────────
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

# ── Jira display-name normalisation map ───────────────────────────────────────
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

# ── Static customer overrides ─────────────────────────────────────────────────
# Keyed by lowercase first-word fragment of the CSO epic name.
# Edit this dict to add/update customers; new customers auto-discovered via Confluence.
STATIC_OVERRIDES = {
    "citizens": {
        "id": "citizens", "jql_keyword": "Citizens",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle", "MySQL", "PostgreSQL"],
        "portal_url": "https://citizens.tessell.com",
        "confluence_page_id": "2164948993",
    },
    "atlas": {
        "id": "atlas-airlines", "jql_keyword": "Atlas Air",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://atlasair.tessell.com/",
        "confluence_page_id": "2165178370",
    },
    "aon": {
        "id": "aon", "jql_keyword": "Aon",
        "cloud": "Azure", "region": "eastus",
        "engines": ["Oracle"],
        "portal_url": "https://aon.tessell.com/",
        "confluence_page_id": "2165407755",
    },
    "usda": {
        "id": "usda-exadata", "jql_keyword": "USDA",
        "cloud": "Azure", "region": "eastus",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165243927",
    },
    "duncan": {
        "id": "duncan-solutions", "jql_keyword": "Duncan",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://duncansolutions.tessell.com/",
        "confluence_page_id": "2165866507",
    },
    "att": {
        "id": "att", "jql_keyword": "ATT",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165243947",
    },
    "boost": {
        "id": "boost-mobile", "jql_keyword": "Boost Mobile",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165800962",
    },
    "smfg": {
        "id": "smfg", "jql_keyword": "SMFG",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://smfg.tessell.com",
        "confluence_page_id": "2165538818",
    },
    "pwc": {
        "id": "pwc-services", "jql_keyword": "PWC",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165604374",
    },
    "advizex": {
        "id": "advizex-solutions", "jql_keyword": "Advizex",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://advizex.tessell.com/",
        "confluence_page_id": "2165899266",
    },
    "levis": {
        "id": "levis-phase-1", "jql_keyword": "Levis",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://levis.tessell.com/",
        "confluence_page_id": "2164916227",
    },
    "williams": {
        "id": "williams", "jql_keyword": "Williams",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://williams.tessell.com/",
        "confluence_page_id": "2165243907",
    },
    "equinor": {
        "id": "equinor", "jql_keyword": "Equinor",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://equinor.tessell.com",
        "confluence_page_id": "2165604354",
    },
    "brocacef": {
        "id": "brocacef-nl", "jql_keyword": "Brocacef",
        "cloud": "Azure", "region": "westeurope",
        "engines": ["Oracle"],
        "portal_url": "https://brocacef.tessell.com/",
        "confluence_page_id": "2165309452",
    },
    "magaya": {
        "id": "magaya", "jql_keyword": "Magaya",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://magaya.tessell.com/",
        "confluence_page_id": "2164719623",
    },
    "darlingii": {
        "id": "darlingii", "jql_keyword": "Darlingii",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://darlingii.tessell.com/",
        "confluence_page_id": "2165932033",
    },
    "onity": {
        "id": "onity-group", "jql_keyword": "Onity",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://onitygroup.tessell.com",
        "confluence_page_id": "2165800982",
    },
    "bhfl": {
        "id": "bhfl", "jql_keyword": "BHFL",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://bhfl.tessell.com/",
        "confluence_page_id": "2165964801",
    },
    "collectors": {
        "id": "collectors", "jql_keyword": "Collectors",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://collectors.tessell.com/",
        "confluence_page_id": "2165702658",
    },
    "usss": {
        "id": "usss", "jql_keyword": "USSS",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "2165997569",
    },
    "landis": {
        "id": "landisgyr", "jql_keyword": "LandisGyr",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://landisgyr.tessell.com",
        "confluence_page_id": "2165768194",
    },
    "sallie": {
        "id": "sallie-mae", "jql_keyword": "Sallie Mae",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "https://salliemae.tessell.com",
        "confluence_page_id": "2165080066",
    },
}
