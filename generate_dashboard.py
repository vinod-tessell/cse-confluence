import os, json, re, requests
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

auth         = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
conf_auth    = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_TOKEN)
headers      = {"Accept": "application/json"}
conf_headers = {"Accept": "application/json", "Content-Type": "application/json"}

# ── Logo colours — cycled by index for auto-generated customers ────────────────
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

# ── Static overrides — anything you want pinned for specific customers ─────────
# Keyed by lowercase customer name fragment for fuzzy matching
STATIC_OVERRIDES = {
    "citizens": {
        "id": "citizens", "jql_keyword": "Citizens",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle", "MySQL", "PostgreSQL"],
        "portal_url": "https://citizens.tessell.com",
        "confluence_page_id": "2164948993",
        "ticket_history": [
            {"month": "Oct 2025", "count": 3}, {"month": "Nov 2025", "count": 5},
            {"month": "Dec 2025", "count": 7}, {"month": "Jan 2026", "count": 6},
            {"month": "Feb 2026", "count": 6}, {"month": "Mar 2026", "count": 8}
        ],
        "pulse": [
            {"sentiment": "frustrated", "text": "Clone to QA blocked 4+ days"},
            {"sentiment": "concerned",  "text": "Perf Insights dark since Nov 2025"},
            {"sentiment": "concerned",  "text": "MySQL ZZ6 HA recurring, no permanent fix"},
            {"sentiment": "waiting",    "text": "Billing download pending engineering"},
            {"sentiment": "positive",   "text": "DB upgrade to 7.64.1 completed smoothly"}
        ]
    },
    "atlas": {
        "id": "atlas-air", "jql_keyword": "Atlas Air",
        "cloud": "AWS", "region": "us-east-1",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "",
        "ticket_history": [], "pulse": []
    },
    "aon": {
        "id": "aon", "jql_keyword": "Aon",
        "cloud": "Azure", "region": "eastus",
        "engines": ["Oracle"],
        "portal_url": "",
        "confluence_page_id": "",
        "ticket_history": [], "pulse": []
    }
}

def find_override(name):
    """Fuzzy match customer name against static overrides."""
    nl = name.lower()
    for key, override in STATIC_OVERRIDES.items():
        if key in nl or nl.startswith(key[:4]):
            return override
    return {}

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

def build_customer_entry(idx, name, status, owner, epic_key, phase_override=None):
    """Build a customer dict from raw Jira epic data + static overrides."""
    owner_short = owner.split()[0] if owner else ""
    phase       = phase_override or status_to_phase(status)
    palette     = LOGO_PALETTE[idx % len(LOGO_PALETTE)]
    override    = find_override(name)
    slug        = override.get("id") or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return {
        "id":                 slug,
        "name":               name,
        "initials":           make_initials(name),
        "logo_color":         palette["logo_color"],
        "logo_bg":            palette["logo_bg"],
        "cloud":              override.get("cloud", "AWS"),
        "region":             override.get("region", "us-east-1"),
        "engines":            override.get("engines", ["Oracle"]),
        "phase":              phase,
        "cse_owner":          owner_short,
        "tam":                override.get("tam", ""),
        "portal_url":         override.get("portal_url", ""),
        "confluence_page_id": override.get("confluence_page_id", ""),
        "jql_keyword":        override.get("jql_keyword", name),
        "active":             True,
        "ticket_history":     override.get("ticket_history", []),
        "pulse":              override.get("pulse", []),
        "cso_epic":           epic_key,
        "cso_status":         status,
    }

def fetch_active_customers():
    """
    Tier 1 — CSO epics where statusCategory != Done (active implementations).
    Tier 2 — CSO epics where statusCategory = Done BUT customer has open
              TS/SR tickets updated in the last 30 days (live operational customers).
    Both tiers are merged, deduped by customer name, and returned.
    """

    # ── Tier 1: In-progress implementations ───────────────────────────────────
    print("Tier 1: Fetching active implementation epics (CSO != Done)...")
    r1 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql",
        auth=auth, headers=headers,
        params={
            "jql": "project = CSO AND issuetype = Epic AND statusCategory != Done ORDER BY updated DESC",
            "maxResults": 50,
            "fields": "summary,status,assignee,created,updated"
        }
    )
    r1.raise_for_status()
    tier1_epics = r1.json().get("issues", [])
    print(f"  Found {len(tier1_epics)} active implementation epics")

    # ── Tier 2: Completed implementations that still have open operational tickets
    print("Tier 2: Fetching completed epics with live TS/SR activity...")
    r2 = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql",
        auth=auth, headers=headers,
        params={
            "jql": "project = CSO AND issuetype = Epic AND statusCategory = Done ORDER BY updated DESC",
            "maxResults": 100,
            "fields": "summary,status,assignee,created,updated"
        }
    )
    r2.raise_for_status()
    done_epics = r2.json().get("issues", [])
    print(f"  Found {len(done_epics)} completed epics — checking for live operational tickets...")

    # For each done epic, check if the customer has any open TS/SR tickets in last 30d
    tier2_epics = []
    for epic in done_epics:
        name = (epic["fields"].get("summary") or "").strip()
        override = find_override(name)
        keyword  = override.get("jql_keyword", name)
        try:
            check = requests.get(
                f"{JIRA_BASE}/rest/api/3/search/jql",
                auth=auth, headers=headers,
                params={
                    "jql": (f'project in (TS, SR) AND text ~ "{keyword}" '
                            f'AND statusCategory != Done AND updated >= -30d'),
                    "maxResults": 1,
                    "fields": "summary"
                }
            )
            if check.status_code == 200 and check.json().get("total", 0) > 0:
                tier2_epics.append(epic)
                print(f"  ✅ {name} — live operational tickets found, including in Tier 2")
        except Exception:
            pass  # skip on error, don't block the whole run

    print(f"  {len(tier2_epics)} completed implementations with active operational tickets")

    # ── Merge tiers, dedupe by name ────────────────────────────────────────────
    seen_names = set()
    customers  = []

    for idx, epic in enumerate(tier1_epics):
        f       = epic["fields"]
        name    = (f.get("summary") or "").strip()
        status  = f.get("status", {}).get("name", "To Do")
        owner   = (f.get("assignee") or {}).get("displayName", "")
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            customers.append(build_customer_entry(idx, name, status, owner, epic["key"]))

    for epic in tier2_epics:
        f       = epic["fields"]
        name    = (f.get("summary") or "").strip()
        owner   = (f.get("assignee") or {}).get("displayName", "")
        if name.lower() not in seen_names:
            seen_names.add(name.lower())
            idx = len(customers)
            # Phase = Steady State for completed implementations still generating tickets
            customers.append(build_customer_entry(
                idx, name, "Done", owner, epic["key"], phase_override="Steady State"
            ))

    print(f"\n  Total customers to process: {len(customers)} "
          f"({len(tier1_epics)} active + {len(tier2_epics)} live operational)")
    return customers

# ── Jira helpers ───────────────────────────────────────────────────────────────
def jql(query, max=20):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql",
        auth=auth, headers=headers,
        params={"jql": query, "maxResults": max,
                "fields": "summary,priority,status,created,resolutiondate,issuetype,labels"}
    )
    r.raise_for_status()
    return r.json().get("issues", [])

def make_jqls(keyword):
    return {
        "p0p1": (
            f'project in (TS, SR) AND text ~ "{keyword}" '
            f'AND labels in (P0, P1) '
            f'AND statusCategory != Done ORDER BY created DESC'
        ),
        "open": (
            f'project in (TS, SR) AND text ~ "{keyword}" '
            f'AND statusCategory != Done ORDER BY created DESC'
        ),
        "features": (
            f'project in (TS, SR) AND text ~ "{keyword}" '
            f'AND issuetype in (Feature, "Feature Request", Story) '
            f'AND statusCategory != Done ORDER BY created DESC'
        ),
        "resolved": (
            f'project in (TS, SR) AND text ~ "{keyword}" '
            f'AND statusCategory = Done AND resolutiondate >= -30d ORDER BY resolutiondate DESC'
        ),
        "recent": (
            f'project in (TS, SR) AND text ~ "{keyword}" '
            f'AND updated >= -30d ORDER BY updated DESC'
        )
    }

def fetch_customer_data(keyword):
    queries = make_jqls(keyword)
    return {
        "p0p1":     jql(queries["p0p1"],     max=10),
        "open":     jql(queries["open"],     max=20),
        "features": jql(queries["features"], max=10),
        "resolved": jql(queries["resolved"], max=50),
        "recent":   jql(queries["recent"],   max=12)
    }

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
    """Read P0/P1 from labels field — the SRE priority label."""
    labels = [l.upper() for l in (fields.get("labels") or [])]
    if "P0" in labels: return "pc", "P0"
    if "P1" in labels: return "ph", "P1"
    return None, None

def priority_class(p):
    """Fallback — Jira priority field for display on non-P0/P1 tickets."""
    p = (p or "").lower()
    if p in ("highest","critical"): return "pc", "Highest"
    if p in ("high",):              return "ph", "High"
    if p in ("medium",):            return "pm", "Medium"
    return "pl", p.capitalize() or "—"

def ticket_row(issue):
    key  = issue["key"]
    f    = issue["fields"]
    summ = (f.get("summary") or "")[:72]
    # Use SRE label P0/P1 if present, otherwise fall back to Jira priority
    sre_pc, sre_pl = sre_priority(f)
    if sre_pc:
        pc, pl = sre_pc, sre_pl
    else:
        pc, pl = priority_class(f.get("priority", {}).get("name", ""))
    sc_, sl = status_class(f.get("status", {}).get("name", ""))
    url  = f"{JIRA_BASE}/browse/{key}"
    return (f'<tr><td><a class="tlink" href="{url}" target="_blank">{key}</a></td>'
            f'<td>{summ}</td><td><span class="pb {pc}">{pl}</span></td>'
            f'<td><span class="sp {sc_}">{sl}</span></td><td>{age_days(f.get("created",""))}</td></tr>')
    s = (s or "").lower()
    if "progress" in s or "review"   in s: return "si",  "In Progress"
    if "pending"  in s or "wait"     in s: return "spe", "Pending Eng"
    if "done"     in s or "closed"   in s or "resolved" in s: return "sc", "Closed"
    return "so", s.capitalize() or "Open"

def ticket_row(issue):
    key  = issue["key"]
    f    = issue["fields"]
    summ = (f.get("summary") or "")[:72]
    pc, pl  = priority_class(f.get("priority",{}).get("name",""))
    sc_, sl = status_class(f.get("status",{}).get("name",""))
    url  = f"{JIRA_BASE}/browse/{key}"
    return (f'<tr><td><a class="tlink" href="{url}" target="_blank">{key}</a></td>'
            f'<td>{summ}</td><td><span class="pb {pc}">{pl}</span></td>'
            f'<td><span class="sp {sc_}">{sl}</span></td><td>{age_days(f.get("created",""))}</td></tr>')

def compute_health(p0p1, open_tickets, features, resolved):
    score   = 10
    pending = len([i for i in open_tickets
                   if 'pending' in (i['fields'].get('status',{}).get('name','') or '').lower()])
    if   len(p0p1) >= 3:  score -= 4
    elif len(p0p1) == 2:  score -= 3
    elif len(p0p1) == 1:  score -= 2
    if   len(open_tickets) >= 10: score -= 2
    elif len(open_tickets) >= 6:  score -= 1
    if   pending >= 4: score -= 2
    elif pending >= 2: score -= 1
    if len(features) >= 5: score -= 1
    if len(resolved) == 0: score -= 1
    score = max(1, min(10, score))
    label = ("Healthy" if score >= 8 else "Stable" if score >= 6
             else "Needs Attention" if score >= 4 else "At Risk")
    color = "#68D391" if score >= 8 else "#FFC107" if score >= 6 else "#FC8181"
    health_key = ("healthy" if score >= 8 else "stable" if score >= 6
                  else "attention" if score >= 4 else "atrisk")
    return score, label, color, health_key, pending

# ── Timeline builder ───────────────────────────────────────────────────────────
def get_changelog(key):
    r = requests.get(f"{JIRA_BASE}/rest/api/3/issue/{key}/changelog",
                     auth=auth, headers=headers, params={"maxResults": 10})
    if r.status_code != 200: return []
    events = []
    for h in r.json().get("values", []):
        ts, author = h.get("created",""), h.get("author",{}).get("displayName","Tessell")
        for item in h.get("items", []):
            field = item.get("field","")
            if field in ("status","priority"):
                events.append({"ts":ts,"key":key,"type":field,
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
                    if inline.get("type") == "text":
                        text += inline.get("text","") + " "
        elif isinstance(body, str):
            text = body
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
            for ev in get_comments(key):  ev["summary"]=summ; all_events.append(ev)
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
        else:
            continue

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
.body{padding:1.25rem 1.5rem}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:1.25rem}
.metric{background:#fff;border-radius:8px;padding:.9rem 1rem;border:.5px solid #DFE1E6}
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
.bar-row{display:flex;align-items:center;gap:6px;padding:4px 1rem}
.blabel{font-size:10px;color:#5E6C84;width:60px;flex-shrink:0}
.btrack{flex:1;height:7px;background:#F4F5F7;border-radius:4px;overflow:hidden}
.bfill{height:100%;border-radius:4px}
.bval{font-size:10px;font-weight:700;width:16px;text-align:right}
.pulse-row{padding:7px 1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:flex-start;gap:7px}
.pulse-row:last-child{border-bottom:none}
.pdot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:3px}
.ptext{font-size:11px;color:#5E6C84;line-height:1.4}
.ptext b{color:#172B4D}
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
"""

NAV_HTML = """<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span>
    <span class="nl active">Customers</span>
    <span class="nl">Incidents</span>
    <span class="nl">Onboarding</span>
  </div>
  {back}
</div>"""

HEALTH_JS = """
function runHealth(DATA) {
  const el = document.getElementById('ai-body');
  const sc = document.getElementById('ai-score');
  let score = 10, findings = [], actions = [];
  if (DATA.p0p1 >= 3)       { score-=4; findings.push(`<b style="color:#FC8181">${DATA.p0p1} active P0 incidents</b> (${DATA.p0keys.join(', ')})`); actions.push(`Escalate ${DATA.p0keys[0]} to engineering leadership for same-day resolution`); }
  else if (DATA.p0p1 === 2) { score-=3; findings.push(`<b style="color:#FC8181">2 active P0 incidents</b> (${DATA.p0keys.join(', ')})`); actions.push(`Escalate ${DATA.p0keys[0]} and ${DATA.p0keys[1]} — both need engineering owner today`); }
  else if (DATA.p0p1 === 1) { score-=2; findings.push(`<b style="color:#FFC107">1 active P0/P1</b> (${DATA.p0keys[0]})`); actions.push(`Ensure ${DATA.p0keys[0]} has daily updates to customer`); }
  else                       { findings.push('<b style="color:#68D391">No active P0/P1 incidents</b>'); }
  if (DATA.open >= 8)        { score-=2; findings.push(`High backlog: <b>${DATA.open} tickets</b> open`); }
  else if (DATA.open >= 5)   { score-=1; findings.push(`Moderate backlog: <b>${DATA.open} open tickets</b>`); }
  else                       { findings.push(`<b style="color:#68D391">Healthy ticket volume</b>: ${DATA.open} open`); }
  if (DATA.pendingEng >= 4)  { score-=2; findings.push(`<b>${DATA.pendingEng} tickets stuck pending engineering</b>`); actions.push(`Review ${DATA.pendingEng} blocked tickets and set ETAs for customer`); }
  else if (DATA.pendingEng >= 2) { score-=1; findings.push(`${DATA.pendingEng} tickets pending engineering`); }
  if (DATA.features >= 5)    { score-=1; findings.push(`Large feature backlog: <b>${DATA.features} requests</b>`); actions.push('Schedule a feature roadmap call to set delivery expectations'); }
  if (DATA.resolved === 0)   { score-=1; findings.push('<b style="color:#FFC107">No tickets resolved in 30 days</b>'); }
  else                       { findings.push(`<b style="color:#68D391">${DATA.resolved} resolved</b> in last 30 days`); }
  score = Math.max(1, Math.min(10, score));
  const color = score>=8?'#68D391':score>=6?'#FFC107':'#FC8181';
  const label = score>=8?'Healthy':score>=6?'Stable':score>=4?'Needs Attention':'At Risk';
  const badge = document.getElementById('health-badge');
  const dot   = document.getElementById('health-dot');
  if (badge) { badge.textContent=label; badge.style.color=color; }
  if (dot)   { dot.style.background=color; }
  if (badge && badge.parentElement) {
    badge.parentElement.style.borderColor = color+'4D';
    badge.parentElement.style.background  = color+'1A';
  }
  let html = findings.map(f=>`<p style="margin-bottom:6px">• ${f}</p>`).join('');
  if (actions.length) html += `<div style="margin-top:8px;padding-top:8px;border-top:.5px solid rgba(255,255,255,0.1)"><p style="font-size:10px;font-weight:700;color:#00C2E0;letter-spacing:.08em;text-transform:uppercase;margin-bottom:5px">Recommended Actions</p>${actions.map(a=>`<p style="margin-bottom:4px">→ ${a}</p>`).join('')}</div>`;
  el.innerHTML = html;
  sc.textContent = score;
  sc.style.color  = color;
  document.getElementById('ai-ts').textContent = 'Assessed: ' + DATA.generated;
}
"""

# ── Customer dashboard builder ─────────────────────────────────────────────────
def build_customer_html(cust, data):
    now     = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    p0p1    = data["p0p1"]
    open_t  = data["open"]
    features= data["features"]
    resolved= data["resolved"]
    timeline= build_timeline(data["recent"])

    score, health_label, health_color, _, pending = compute_health(p0p1, open_t, features, resolved)
    p0_keys   = [i["key"] for i in p0p1[:3]]
    high_keys = [i["key"] for i in open_t
                 if (i['fields'].get('priority',{}).get('name','') or '').lower()
                 in ('high','p1','highest')][:3]

    p0_rows = "".join(ticket_row(i) for i in p0p1[:5]) or \
        '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No active P0/P1 incidents</td></tr>'
    tk_rows = "".join(ticket_row(i) for i in open_t[:10]) or \
        '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No open tickets</td></tr>'

    feat_items = ""
    for i in features[:5]:
        key  = i["key"]
        summ = (i["fields"].get("summary") or "")[:65]
        url  = f"{JIRA_BASE}/browse/{key}"
        sc_, sl = status_class(i["fields"].get("status",{}).get("name",""))
        feat_items += (f'<div class="fr-item"><div class="fr-icon" style="background:#E6F1FB">💡</div>'
                       f'<div class="fr-content"><div class="fr-title">{summ}</div>'
                       f'<div class="fr-meta"><a class="tlink" href="{url}" target="_blank">{key}</a></div></div>'
                       f'<span class="fr-status {sc_}">{sl}</span></div>')

    # Ticket history bars
    bar_max   = max((h["count"] for h in cust.get("ticket_history",[])), default=1)
    bar_colors= ["#38A169","#38A169","#D69E2E","#DD6B20","#DD6B20","#E53E3E"]
    bars = ""
    for idx, h in enumerate(cust.get("ticket_history", [])[-6:]):
        pct   = round(h["count"] / bar_max * 100)
        col   = bar_colors[min(idx, len(bar_colors)-1)]
        month = h["month"].split()[0][:3] + " " + h["month"].split()[-1][-2:]
        bars += (f'<div class="bar-row"><span class="blabel">{month}</span>'
                 f'<div class="btrack"><div class="bfill" style="width:{pct}%;background:{col}"></div></div>'
                 f'<span class="bval" style="color:{col}">{h["count"]}</span></div>')

    # Pulse
    pulse_colors = {"frustrated":"#E53E3E","concerned":"#DD6B20","waiting":"#D69E2E","positive":"#38A169","neutral":"#5E6C84"}
    pulse_html = ""
    for p in cust.get("pulse", []):
        col  = pulse_colors.get(p["sentiment"], "#5E6C84")
        sent = p["sentiment"].capitalize()
        pulse_html += (f'<div class="pulse-row"><div class="pdot" style="background:{col}"></div>'
                       f'<div class="ptext"><b>{sent}</b> — {p["text"]}</div></div>')
    if not pulse_html:
        pulse_html = '<div class="pulse-row"><div class="ptext">No pulse data yet.</div></div>'

    # Quick links
    ql_jira = f'{JIRA_BASE}/issues/?jql=text+~+%22{cust["jql_keyword"].replace(" ","+")}.%22+AND+statusCategory+!%3D+Done'
    portal  = cust.get("portal_url","")
    portal_link = f'<div class="ir"><a class="tlink" href="{portal}" target="_blank">{portal}</a></div>' if portal else ""

    data_js = json.dumps({
        "p0p1": len(p0p1), "open": len(open_t),
        "features": len(features), "resolved": len(resolved),
        "pendingEng": pending, "p0keys": p0_keys,
        "highKeys": high_keys, "generated": now
    })

    mv_col   = "red" if len(p0p1)>0 else "green"
    open_col = "orange" if len(open_t)>5 else "yellow"

    nav  = NAV_HTML.format(back=f'<a class="nav-back" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/{CONFLUENCE_PARENT}" target="_parent">← All Customers</a>')
    engines_str = " · ".join(cust["engines"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{cust['name']} — Customer Dashboard</title>
<style>{SHARED_CSS}</style>
</head>
<body>
{nav}
<div style="background:#0B1F45;padding:1.1rem 1.5rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;border-bottom:1px solid #122752">
  <div style="display:flex;align-items:center;gap:10px">
    <div style="width:42px;height:42px;background:{cust['logo_bg']};border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:{cust['logo_color']}">{cust['initials']}</div>
    <div>
      <div style="font-size:18px;font-weight:700;color:#fff">{cust['name']}</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px">{cust['cloud']} · {cust['region']} · {engines_str} · {cust['phase']}</div>
    </div>
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
  <div class="metrics">
    <div class="metric"><div class="mlabel">Open P0/P1</div><div class="mval {mv_col}">{len(p0p1)}</div><div class="msub">Active critical issues</div></div>
    <div class="metric"><div class="mlabel">Open Tickets</div><div class="mval {open_col}">{len(open_t)}</div><div class="msub">Across all priorities</div></div>
    <div class="metric"><div class="mlabel">Feature Requests</div><div class="mval blue">{len(features)}</div><div class="msub">Pending delivery</div></div>
    <div class="metric"><div class="mlabel">Resolved (30d)</div><div class="mval green">{len(resolved)}</div><div class="msub">Last 30 days</div></div>
    <div class="metric"><div class="mlabel">Health Score</div><div class="mval" style="color:{health_color}">{score}/10</div><div class="msub">Rule-based</div></div>
  </div>
  <div class="grid2">
    <div>
      <div class="ai-panel">
        <div class="ai-eyebrow">✦ Health Analysis</div>
        <div class="ai-title">Customer Health Assessment</div>
        <div class="ai-body" id="ai-body">Calculating...</div>
        <div class="ai-footer">
          <div style="display:flex;align-items:baseline;gap:4px">
            <span class="ai-score-label">Health score</span>
            <span class="ai-score-val" id="ai-score" style="color:{health_color}">{score}</span>
            <span class="ai-score-max">/10</span>
          </div>
          <span id="ai-ts" class="ai-ts"></span>
        </div>
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">🚨 Active P0 / P1 Incidents</span><span class="badge br">{len(p0p1)} Open</span></div>
        <table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{p0_rows}</tbody></table>
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">🎫 Open Support Tickets</span><span class="badge bo">{len(open_t)} Open</span></div>
        <table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{tk_rows}</tbody></table>
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">💡 Feature Requests</span><span class="badge bb">{len(features)} Active</span></div>
        {feat_items or '<p style="padding:1rem;font-size:12px;color:#5E6C84">No open feature requests.</p>'}
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">📅 Recent Activity</span><span class="badge bg">Live</span></div>
        <div class="tl">{timeline}</div>
      </div>
    </div>
    <div>
      <div class="sb-sec">
        <div class="sb-head">🏢 Account Details</div>
        <div class="ir"><span class="ilabel">Account</span><span class="ival">{cust['name']}</span></div>
        <div class="ir"><span class="ilabel">CSE Owner</span><span class="ival">{cust.get('cse_owner','—')}</span></div>
        <div class="ir"><span class="ilabel">TAM / TPM</span><span class="ival">{cust.get('tam','—')}</span></div>
        <div class="ir"><span class="ilabel">Cloud</span><span class="ival">{cust['cloud']} · {cust['region']}</span></div>
        <div class="ir"><span class="ilabel">Engines</span><span class="ival">{engines_str}</span></div>
        <div class="ir"><span class="ilabel">Phase</span><span class="ival">{cust['phase']}</span></div>
        {portal_link}
      </div>
      {'<div class="sb-sec"><div class="sb-head">📊 Ticket Volume</div><div style="padding:8px 0 4px">' + bars + '</div></div>' if bars else ''}
      <div class="sb-sec">
        <div class="sb-head">💬 Customer Pulse</div>
        {pulse_html}
      </div>
      <div class="sb-sec">
        <div class="sb-head">🔗 Quick Links</div>
        <div class="ir"><a class="tlink" href="{ql_jira}" target="_blank">All Open Tickets</a></div>
        <div class="ir"><a class="tlink" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/{CONFLUENCE_PARENT}" target="_blank">Customer Portfolio</a></div>
        {portal_link}
      </div>
    </div>
  </div>
</div>
<script>
const DATA = {data_js};
{HEALTH_JS}
window.onload = () => runHealth(DATA);
</script>
</body>
</html>"""

# ── Master dashboard builder ───────────────────────────────────────────────────
def build_master_html(customer_results):
    now       = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    real      = [c for c in customer_results if c["config"].get("name")]
    total     = len(real)
    at_risk   = sum(1 for c in real if c["health_key"] == "atrisk")
    attention = sum(1 for c in real if c["health_key"] == "attention")
    healthy   = sum(1 for c in real if c["health_key"] in ("healthy","stable"))
    total_p0  = sum(c["p0_count"] for c in real)

    # ── Customer cards (for the "All Customers" section at bottom) ─────────────
    cards = ""
    for cr in customer_results:
        cust = cr["config"]
        if not cust.get("name"):
            continue
        hk    = cr["health_key"]
        hl    = cr["health_label"]
        hcol  = cr["health_color"]
        p0col = "red"    if cr["p0_count"] > 0     else "green"
        tkcol = "orange" if cr["open_count"] > 5   else "gray" if cr["open_count"] > 2 else "green"
        tags  = "".join(f'<span class="tag">{e}</span>' for e in cust["engines"]) + \
                f'<span class="tag">{cust["cloud"]}</span>'
        url   = cr.get("dashboard_url","#")
        phase_emoji = {"Onboarding":"🔵","Implementation":"🟡","Stabilisation":"🟠",
                       "Production":"🟢","Steady State":"⚫"}.get(cust["phase"],"")
        cards += f"""<a class="cust-card" data-health="{hk}" data-name="{cust['name'].lower()}" href="{url}" target="_parent" style="text-decoration:none">
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

    # ── Action required items — top 3 by severity ─────────────────────────────
    action_items = []
    for cr in sorted(customer_results, key=lambda x: x["p0_count"], reverse=True)[:3]:
        c = cr["config"]
        if cr["p0_count"] > 0:
            sev, sev_cls = "Critical", "sev-critical"
            title = f"{c['name']} — {cr['p0_count']} P0{'s' if cr['p0_count']>1 else ''} open"
            desc  = f"{cr['open_count']} total open tickets. Immediate engineering escalation required."
        elif cr["open_count"] > 5:
            sev, sev_cls = "High", "sev-high"
            title = f"{c['name']} — {cr['open_count']} open tickets"
            desc  = f"{cr['feat_count']} feature requests pending. Review backlog priority with engineering."
        else:
            sev, sev_cls = "Watch", "sev-watch"
            title = f"{c['name']} — monitor closely"
            desc  = f"Phase: {c['phase']}. {cr['open_count']} open tickets, {cr['feat_count']} feature requests."
        url = cr.get("dashboard_url","#")
        action_items.append(
            f'<div class="action-item">'
            f'<span class="ai-severity {sev_cls}">{sev}</span>'
            f'<div class="ai-title">{title}</div>'
            f'<div class="ai-desc">{desc}</div>'
            f'<a class="ai-link" href="{url}" target="_parent">→ View Dashboard</a>'
            f'</div>'
        )
    # pad to 3
    while len(action_items) < 3:
        action_items.append('<div class="action-item"><span class="ai-severity sev-watch">Watch</span><div class="ai-title">No further escalations</div><div class="ai-desc">Remaining customers are healthy or in early implementation.</div></div>')

    # ── Pipeline counts ────────────────────────────────────────────────────────
    phase_counts = {"Onboarding":0,"Implementation":0,"Stabilisation":0,"Production":0,"Steady State":0}
    for cr in customer_results:
        p = cr["config"].get("phase","")
        if p in phase_counts: phase_counts[p] += 1
    pipe_max = max(phase_counts.values()) or 1

    def pipe_row(label, count, color, text_color):
        pct = round(count / pipe_max * 100)
        return (f'<div class="phase-row">'
                f'<span class="phase-label">{label}</span>'
                f'<div class="phase-track"><div class="phase-fill" style="width:{max(pct,8)}%;background:{color};color:{text_color}">{count if pct>15 else ""}</div></div>'
                f'<span class="phase-count" style="color:{color}">{count}</span>'
                f'</div>')

    pipeline_html = (
        pipe_row("Onboarding",    phase_counts["Onboarding"],    "#378ADD","#E6F1FB") +
        pipe_row("Implementation",phase_counts["Implementation"],"#BA7517","#FAEEDA") +
        pipe_row("Stabilisation", phase_counts["Stabilisation"], "#E24B4A","#FCEBEB") +
        pipe_row("Production",    phase_counts["Production"],    "#1D9E75","#E1F5EE") +
        pipe_row("Steady State",  phase_counts["Steady State"],  "#5F5E5A","#F1EFE8")
    )

    # ── Health heatmap cells ───────────────────────────────────────────────────
    heatmap_cells = ""
    for cr in customer_results:
        c   = cr["config"]
        hk  = cr["health_key"]
        cls = {"atrisk":"hm-risk","attention":"hm-warn","stable":"hm-stable","healthy":"hm-good"}.get(hk,"hm-stable")
        stat = f"{cr['p0_count']} P0s · {cr['open_count']} open" if cr["p0_count"] > 0 else f"{cr['open_count']} open · {c['phase'][:12]}"
        url  = cr.get("dashboard_url","#")
        heatmap_cells += (
            f'<a class="hm-cell {cls}" href="{url}" target="_parent" style="text-decoration:none">'
            f'<div class="hm-name">{c["name"][:18]}</div>'
            f'<div class="hm-stat">{stat}</div>'
            f'</a>'
        )

    # ── Owner summary ──────────────────────────────────────────────────────────
    owner_map = {}
    for cr in customer_results:
        owner = cr["config"].get("cse_owner","—") or "—"
        if owner not in owner_map:
            owner_map[owner] = {"p0":0,"open":0,"customers":[]}
        owner_map[owner]["p0"]   += cr["p0_count"]
        owner_map[owner]["open"] += cr["open_count"]
        owner_map[owner]["customers"].append(cr["config"]["name"].split()[0])

    avatar_colors = [
        {"bg":"#E6F1FB","col":"#0C447C"},{"bg":"#EEEDFE","col":"#3C3489"},
        {"bg":"#EAF3DE","col":"#27500A"},{"bg":"#FAEEDA","col":"#633806"},
        {"bg":"#FBEAF0","col":"#72243E"},{"bg":"#E1F5EE","col":"#085041"},
    ]
    owner_rows = ""
    for idx,(owner,data) in enumerate(sorted(owner_map.items(), key=lambda x:-x[1]["p0"])[:5]):
        ac    = avatar_colors[idx % len(avatar_colors)]
        parts = owner.split()
        initials = (parts[0][0]+(parts[1][0] if len(parts)>1 else parts[0][-1])).upper() if parts else "—"
        custs = ", ".join(data["customers"][:3]) + ("…" if len(data["customers"])>3 else "")
        p0col = "#E53E3E" if data["p0"]>0 else "#D69E2E"
        tkcol = "#DD6B20" if data["open"]>5 else "#D69E2E" if data["open"]>2 else "#38A169"
        owner_rows += (
            f'<div class="owner-row">'
            f'<div class="owner-info">'
            f'<div class="owner-avatar" style="background:{ac["bg"]};color:{ac["col"]}">{initials}</div>'
            f'<div><div class="owner-name">{owner}</div><div class="owner-meta">{custs}</div></div>'
            f'</div>'
            f'<div class="owner-counts">'
            f'<div class="oc"><div class="oc-val" style="color:{p0col}">{data["p0"]}</div><div class="oc-label">P0s</div></div>'
            f'<div class="oc"><div class="oc-val" style="color:{tkcol}">{data["open"]}</div><div class="oc-label">Open</div></div>'
            f'</div></div>'
        )

    # ── Resolution trend bars ──────────────────────────────────────────────────
    top_by_tickets = sorted([cr for cr in customer_results if cr["open_count"]>0],
                             key=lambda x:-x["open_count"])[:5]
    trend_max = top_by_tickets[0]["open_count"] if top_by_tickets else 1
    trend_rows = ""
    for cr in top_by_tickets:
        pct  = round(cr["open_count"] / trend_max * 100)
        col  = "#E53E3E" if cr["p0_count"]>0 else "#DD6B20" if cr["open_count"]>5 else "#38A169"
        name = cr["config"]["name"].split()[0][:10]
        trend_rows += (
            f'<div class="trend-row">'
            f'<span class="trend-label">{name}</span>'
            f'<div class="trend-bar-wrap"><div class="trend-bar" style="width:{pct}%;background:{col}"></div></div>'
            f'<span class="trend-val" style="color:{col}">{cr["open_count"]}</span>'
            f'</div>'
        )

    # ── This week highlights ───────────────────────────────────────────────────
    highlights = []
    crit = [cr for cr in customer_results if cr["p0_count"]>0]
    if crit:
        names = ", ".join(c["config"]["name"].split()[0] for c in crit[:2])
        highlights.append(f'🚨 <span style="color:#172B4D;font-weight:600">{sum(c["p0_count"] for c in crit)} P0/P1s open</span> — {names} need immediate attention')
    new_impl = [cr for cr in customer_results if cr["config"].get("phase") in ("Onboarding","Implementation")]
    if new_impl:
        highlights.append(f'🔄 <span style="color:#172B4D;font-weight:600">{len(new_impl)} customers</span> actively in implementation — review velocity in sprint planning')
    prod = [cr for cr in customer_results if cr["config"].get("phase") == "Production"]
    if prod:
        highlights.append(f'✅ <span style="color:#172B4D;font-weight:600">{len(prod)} customers</span> in Production phase')
    highlights.append(f'📋 <span style="color:#172B4D;font-weight:600">{total} total customers</span> tracked across CSE — {healthy} healthy, {at_risk} at risk')
    highlights_html = "".join(
        f'<div style="font-size:11px;color:#5E6C84;line-height:1.7;border-bottom:0.5px solid #F4F5F7;padding-bottom:.6rem;margin-bottom:.6rem">{h}</div>'
        for h in highlights[:4]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
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
.sev-critical{{background:#FFF5F5;color:#A32D2D}}
.sev-high{{background:#FFFAF0;color:#854F0B}}
.sev-watch{{background:#E6F1FB;color:#0C447C}}
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
.heatmap{{padding:.9rem 1.1rem;display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}
.hm-cell{{border-radius:6px;padding:7px 8px;cursor:pointer;transition:filter .15s;text-decoration:none;display:block}}
.hm-cell:hover{{filter:brightness(0.93)}}
.hm-name{{font-size:10px;font-weight:600;line-height:1.3;margin-bottom:2px}}
.hm-stat{{font-size:10px;opacity:.75}}
.hm-risk{{background:#FFF5F5;border:.5px solid #F09595}}
.hm-risk .hm-name,.hm-risk .hm-stat{{color:#A32D2D}}
.hm-warn{{background:#FFFAF0;border:.5px solid #EF9F27}}
.hm-warn .hm-name,.hm-warn .hm-stat{{color:#854F0B}}
.hm-stable{{background:#E6F1FB;border:.5px solid #85B7EB}}
.hm-stable .hm-name,.hm-stable .hm-stat{{color:#0C447C}}
.hm-good{{background:#EAF3DE;border:.5px solid #97C459}}
.hm-good .hm-name,.hm-good .hm-stat{{color:#27500A}}
.sb-sec{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.1rem}}
.sb-head{{padding:.7rem 1rem;border-bottom:.5px solid #DFE1E6;font-size:12px;font-weight:700;color:#172B4D}}
.owner-row{{display:flex;align-items:center;justify-content:space-between;padding:7px 1rem;border-bottom:.5px solid #DFE1E6}}
.owner-row:last-child{{border-bottom:none}}
.owner-info{{display:flex;align-items:center;gap:8px}}
.owner-avatar{{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0}}
.owner-name{{font-size:12px;font-weight:600;color:#172B4D}}
.owner-meta{{font-size:10px;color:#5E6C84}}
.owner-counts{{display:flex;gap:8px}}
.oc{{text-align:center}}
.oc-val{{font-size:13px;font-weight:700}}
.oc-label{{font-size:9px;color:#5E6C84}}
.trend-row{{display:flex;align-items:center;gap:8px;padding:6px 1rem;border-bottom:.5px solid #DFE1E6}}
.trend-row:last-child{{border-bottom:none}}
.trend-label{{font-size:11px;color:#5E6C84;width:60px;flex-shrink:0}}
.trend-bar-wrap{{flex:1;height:6px;background:#F4F5F7;border-radius:3px;overflow:hidden}}
.trend-bar{{height:100%;border-radius:3px}}
.trend-val{{font-size:11px;font-weight:700;width:20px;text-align:right;flex-shrink:0}}
.cards-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:1.1rem}}
.cust-card{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;cursor:pointer;transition:transform .15s}}
.cust-card:hover{{transform:translateY(-2px)}}
.card-header{{padding:.9rem 1rem .75rem;border-bottom:.5px solid #F4F5F7;display:flex;align-items:center;gap:10px}}
.card-logo{{width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:800;flex-shrink:0}}
.card-name{{font-size:12px;font-weight:700;color:#172B4D;margin-bottom:1px}}
.card-meta{{font-size:10px;color:#5E6C84}}
.health-pill{{margin-left:auto;padding:3px 8px;border-radius:20px;font-size:10px;font-weight:700;display:flex;align-items:center;gap:4px;flex-shrink:0}}
.hp-dot{{width:6px;height:6px;border-radius:50%}}
.card-body{{padding:.75rem 1rem}}
.card-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:.7rem}}
.cs{{text-align:center}}
.cs-val{{font-size:17px;font-weight:700;line-height:1}}
.cs-label{{font-size:10px;color:#5E6C84;margin-top:2px}}
.card-tags{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:.7rem}}
.tag{{font-size:10px;padding:2px 6px;border-radius:4px;background:#F4F5F7;color:#5E6C84;font-weight:500}}
.card-footer{{display:flex;align-items:center;justify-content:space-between;padding-top:.6rem;border-top:.5px solid #F4F5F7}}
.phase-lbl{{font-size:10px;font-weight:600;color:#5E6C84}}
.drill-btn{{font-size:11px;font-weight:600;color:#1A6FDB}}
.sec-divider{{font-size:13px;font-weight:700;color:#172B4D;margin:1.25rem 0 .75rem;display:flex;align-items:center;gap:8px}}
.sec-divider::after{{content:'';flex:1;height:0.5px;background:#DFE1E6}}
.filter-bar{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.filter-btn{{font-size:11px;font-weight:500;padding:4px 12px;border-radius:20px;border:.5px solid #DFE1E6;background:#fff;color:#5E6C84;cursor:pointer}}
.filter-btn.active{{background:#0B1F45;color:#fff;border-color:#0B1F45}}
.search-input{{flex:1;max-width:220px;padding:5px 12px;border-radius:20px;border:.5px solid #DFE1E6;font-size:12px;outline:none;background:#fff;color:#172B4D}}
</style>
</head>
<body>
{NAV_HTML.format(back=f'<span style="font-size:10px;color:rgba(255,255,255,0.3)">Refreshed: {now}</span>')}

<div class="hero">
  <div class="hero-top">
    <div style="display:flex;align-items:center;gap:10px">
      <div class="wordmark-bar"></div>
      <div>
        <div style="font-size:20px;font-weight:700;color:#fff">Customer Success Portfolio</div>
        <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:2px">Executive overview · Tessell CSE · Auto-refreshed from Jira every 30 minutes</div>
      </div>
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
      <div class="action-head-title">
        <span style="font-size:14px">🔴</span> Action Required
        <span class="action-head-badge">{min(3,len([cr for cr in customer_results if cr['p0_count']>0 or cr['open_count']>5]))} items</span>
      </div>
      <span class="action-head-ts">Auto-generated · {now}</span>
    </div>
    <div class="action-items">{''.join(action_items)}</div>
  </div>

  <div class="main-grid">
    <div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">Implementation pipeline</span><span class="sec-sub">{total} total customers</span></div>
        <div class="pipeline">{pipeline_html}</div>
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">Open ticket load by customer</span><span class="sec-sub">Top 5</span></div>
        <div style="padding:6px 0 4px">{trend_rows}</div>
      </div>
    </div>
    <div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">Customer health heatmap</span><span class="sec-sub">Click any cell to drill in</span></div>
        <div class="heatmap">{heatmap_cells}</div>
      </div>
    </div>
    <div>
      <div class="sb-sec">
        <div class="sb-head">CSE ownership summary</div>
        {owner_rows}
      </div>
      <div class="sb-sec">
        <div class="sb-head">This week's highlights</div>
        <div style="padding:.75rem 1rem">{highlights_html}</div>
      </div>
    </div>
  </div>

  <div class="sec-divider">All Customers <div class="filter-bar" style="margin:0"><button class="filter-btn active" onclick="filterCards('all',this)">All</button><button class="filter-btn" onclick="filterCards('atrisk',this)">At Risk</button><button class="filter-btn" onclick="filterCards('attention',this)">Needs Attention</button><button class="filter-btn" onclick="filterCards('healthy',this)">Healthy</button><button class="filter-btn" onclick="filterCards('stable',this)">Stable</button><input class="search-input" type="text" placeholder="Search..." oninput="searchCards(this.value)"/></div></div>

  <div class="cards-grid">{cards}</div>

</div>
<script>
function filterCards(h,btn){{document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.cust-card,[data-health]').forEach(el=>{{el.style.display=h==='all'||el.dataset.health===h?'':'none';}});}}
function searchCards(q){{q=q.toLowerCase();document.querySelectorAll('.cust-card').forEach(el=>{{el.style.display=(el.dataset.name||'').includes(q)?'':'none';}});}}
</script>
</body>
</html>"""

# ── Confluence page manager ────────────────────────────────────────────────────
def ensure_confluence_page(cust, dashboard_url):
    """Create the Confluence page if it doesn't exist yet, return the page ID."""
    page_id = cust.get("confluence_page_id","").strip()
    iframe_body = json.dumps({
        "version": 1, "type": "doc",
        "content": [{"type":"extension","attrs":{
            "extensionType":"com.atlassian.confluence.macro.core",
            "extensionKey":"iframe",
            "parameters":{"macroParams":{
                "src":{"value": dashboard_url},
                "width":{"value":"100%"},
                "height":{"value":"900px"},
                "frameborder":{"value":"0"},
                "scrolling":{"value":"yes"}
            }},
            "layout":"full-width"
        }}]
    })

    if page_id:
        # Update existing page to bump cache
        r = requests.put(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages/{page_id}",
            auth=conf_auth, headers=conf_headers,
            json={
                "id": page_id,
                "status": "current",
                "title": f"{cust['name']} — Customer Dashboard",
                "body": {"representation":"atlas_doc_format","value": iframe_body}
            }
        )
        if r.status_code in (200, 204):
            print(f"  ✅ Updated Confluence page {page_id} for {cust['name']}")
        else:
            print(f"  ⚠️  Could not update page {page_id}: {r.status_code}")
        return page_id
    else:
        # Create new page
        r = requests.post(
            f"{CONFLUENCE_BASE}/wiki/api/v2/pages",
            auth=conf_auth, headers=conf_headers,
            json={
                "spaceId": CONFLUENCE_SPACE,
                "parentId": CONFLUENCE_PARENT,
                "status": "current",
                "title": f"{cust['name']} — Customer Dashboard",
                "body": {"representation":"atlas_doc_format","value": iframe_body}
            }
        )
        if r.status_code == 200:
            new_id = r.json()["id"]
            print(f"  ✅ Created Confluence page {new_id} for {cust['name']}")
            # Write back to customers.json
            cust["confluence_page_id"] = new_id
            return new_id
        else:
            print(f"  ⚠️  Could not create page for {cust['name']}: {r.status_code} {r.text[:200]}")
            return ""

def save_customers_json():
    with open("customers.json","w") as f:
        json.dump(CUSTOMERS, f, indent=2)

# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # ── Auto-generate customer list from CSO Jira epics ───────────────────────
    CUSTOMERS = fetch_active_customers()

    # Save snapshot of what was generated for debugging / audit trail
    with open("customers.json", "w") as f:
        json.dump(CUSTOMERS, f, indent=2)
    print(f"  Saved {len(CUSTOMERS)} customers to customers.json")

    customer_results = []
    pages_updated    = False

    for cust in CUSTOMERS:
        print(f"\n── {cust['name']} ({cust['cso_epic']} · {cust['cso_status']}) ──")
        print(f"  Fetching Jira support data (keyword: {cust['jql_keyword']})...")
        try:
            data = fetch_customer_data(cust["jql_keyword"])
        except Exception as e:
            print(f"  ⚠️  Jira fetch failed: {e}")
            customer_results.append({
                "config": cust, "health_key": "stable", "health_label": "Unknown",
                "health_color": "#5E6C84", "p0_count": 0, "open_count": 0,
                "feat_count": 0, "dashboard_url": "#"
            })
            continue

        print(f"  P0/P1:{len(data['p0p1'])}  Open:{len(data['open'])}  "
              f"Features:{len(data['features'])}  Resolved(30d):{len(data['resolved'])}")

        score, label, color, hk, _ = compute_health(
            data["p0p1"], data["open"], data["features"], data["resolved"]
        )

        # Build HTML file
        html     = build_customer_html(cust, data)
        filename = f"{cust['id']}_dashboard.html"
        with open(filename, "w") as f:
            f.write(html)
        print(f"  ✅ Written {filename}")

        gh_url  = f"https://vinod-tessell.github.io/cse-confluence/{filename}"
        page_id = ensure_confluence_page(cust, gh_url)
        if page_id and page_id != cust.get("confluence_page_id", ""):
            cust["confluence_page_id"] = page_id
            pages_updated = True

        conf_url = (f"https://tessell.atlassian.net/wiki/spaces/CSE/pages/{page_id}"
                    if page_id else "#")

        customer_results.append({
            "config": cust, "health_key": hk, "health_label": label,
            "health_color": color, "p0_count": len(data["p0p1"]),
            "open_count": len(data["open"]), "feat_count": len(data["features"]),
            "dashboard_url": conf_url
        })

    # Save updated confluence_page_ids back
    if pages_updated:
        with open("customers.json", "w") as f:
            json.dump(CUSTOMERS, f, indent=2)
        print("\n✅ customers.json updated with new Confluence page IDs")

    # Build master dashboard
    print("\n── Master Dashboard ────────────────────────────")
    master = build_master_html(customer_results)
    with open("master_dashboard.html", "w") as f:
        f.write(master)
    print("✅ master_dashboard.html written")
    print("\nAll done!")
