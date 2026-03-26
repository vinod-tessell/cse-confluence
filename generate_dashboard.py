import os, json, re, requests
from datetime import datetime, timezone
from requests.auth import HTTPBasicAuth

JIRA_BASE  = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_API_TOKEN"]

auth    = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
headers = {"Accept": "application/json"}

# ── JQL queries ────────────────────────────────────────────────────────────────
JQL_P0P1 = (
    'project in (TS, SR) AND text ~ "Citizens" '
    'AND priority in (P0, P1, Highest, Critical) '
    'AND statusCategory != Done ORDER BY created DESC'
)
JQL_OPEN = (
    'project in (TS, SR) AND text ~ "Citizens" '
    'AND statusCategory != Done ORDER BY priority ASC, created DESC'
)
JQL_FEATURES = (
    'project in (TS, SR) AND text ~ "Citizens" '
    'AND issuetype in (Feature, "Feature Request", Story) '
    'AND statusCategory != Done ORDER BY created DESC'
)
JQL_RESOLVED_30D = (
    'project in (TS, SR) AND text ~ "Citizens" '
    'AND statusCategory = Done '
    'AND resolutiondate >= -30d ORDER BY resolutiondate DESC'
)
JQL_RECENT_UPDATED = (
    'project in (TS, SR) AND text ~ "Citizens" '
    'AND updated >= -30d ORDER BY updated DESC'
)

def jql(query, max=20):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql",
        auth=auth, headers=headers,
        params={"jql": query, "maxResults": max,
                "fields": "summary,priority,status,created,resolutiondate,issuetype"}
    )
    r.raise_for_status()
    return r.json().get("issues", [])

def fmt_date(iso):
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%b %d, %Y")
    except:
        return iso[:10]

def age_days(iso):
    if not iso:
        return "—"
    try:
        created = datetime.fromisoformat(iso[:19]).replace(tzinfo=timezone.utc)
        delta   = datetime.now(timezone.utc) - created
        d = delta.days
        return f"{d}d" if d > 0 else "today"
    except:
        return "—"

def priority_class(p):
    p = (p or "").lower()
    if p in ("p0","critical","highest"):  return "pc", "P0"
    if p in ("p1","high"):                return "ph", "High"
    if p in ("p2","medium"):              return "pm", "Medium"
    return "pl", p.capitalize() or "—"

def status_class(s):
    s = (s or "").lower()
    if "progress" in s or "review" in s: return "si", "In Progress"
    if "pending"  in s or "wait"   in s: return "spe", "Pending Eng"
    if "done"     in s or "closed" in s or "resolved" in s: return "sc", "Closed"
    return "so", s.capitalize() or "Open"

def ticket_row(issue):
    key  = issue["key"]
    f    = issue["fields"]
    summ = (f.get("summary") or "")[:72]
    pc, pl  = priority_class(f.get("priority",{}).get("name",""))
    sc_, sl = status_class(f.get("status",{}).get("name",""))
    ag   = age_days(f.get("created",""))
    url  = f"{JIRA_BASE}/browse/{key}"
    return (
        f'<tr>'
        f'<td><a class="tlink" href="{url}" target="_blank">{key}</a></td>'
        f'<td>{summ}</td>'
        f'<td><span class="pb {pc}">{pl}</span></td>'
        f'<td><span class="sp {sc_}">{sl}</span></td>'
        f'<td>{ag}</td>'
        f'</tr>'
    )

def get_changelog(key):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/issue/{key}/changelog",
        auth=auth, headers=headers,
        params={"maxResults": 10}
    )
    if r.status_code != 200:
        return []
    events = []
    for history in r.json().get("values", []):
        ts     = history.get("created", "")
        author = history.get("author", {}).get("displayName", "Tessell")
        for item in history.get("items", []):
            field  = item.get("field", "")
            from_s = item.get("fromString", "") or ""
            to_s   = item.get("toString",   "") or ""
            if field in ("status", "priority"):
                events.append({
                    "ts": ts, "key": key, "type": field,
                    "from": from_s, "to": to_s, "author": author
                })
    return events

def get_comments(key, max=2):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/issue/{key}/comment",
        auth=auth, headers=headers,
        params={"maxResults": max, "orderBy": "-created"}
    )
    if r.status_code != 200:
        return []
    comments = []
    for c in r.json().get("comments", []):
        body = c.get("body", {})
        text = ""
        if isinstance(body, dict):
            for block in body.get("content", []):
                for inline in block.get("content", []):
                    if inline.get("type") == "text":
                        text += inline.get("text", "") + " "
        elif isinstance(body, str):
            text = body
        text = text.strip()[:120]
        if text:
            comments.append({
                "ts":     c.get("created", ""),
                "key":    key,
                "type":   "comment",
                "author": c.get("author", {}).get("displayName", "Tessell"),
                "text":   text
            })
    return comments

def build_timeline(recent_issues, limit=8):
    all_events = []
    for issue in recent_issues[:12]:
        key  = issue["key"]
        summ = (issue["fields"].get("summary") or "")[:70]
        all_events.append({"ts": issue["fields"].get("created",""), "key": key, "type": "created", "summary": summ})
        try:
            for ev in get_changelog(key):
                ev["summary"] = summ
                all_events.append(ev)
        except: pass
        try:
            for ev in get_comments(key):
                ev["summary"] = summ
                all_events.append(ev)
        except: pass

    def sort_key(e):
        try:    return datetime.fromisoformat(e["ts"][:19])
        except: return datetime.min
    all_events.sort(key=sort_key, reverse=True)

    seen_keys = set()
    timeline  = []
    for ev in all_events:
        k, t   = ev["key"], ev["type"]
        ts_fmt = fmt_date(ev.get("ts",""))
        url    = f"{JIRA_BASE}/browse/{k}"
        summ   = ev.get("summary","")
        if t == "created" and k in seen_keys: continue

        if t == "status":
            to_l = ev["to"].lower()
            if any(x in to_l for x in ("done","resolved","closed")):
                icon,bg,title,desc = "✅","#EAF3DE",f"{k} resolved — {summ}",f"Status → {ev['to']} by {ev['author']}"
            elif "progress" in to_l:
                icon,bg,title,desc = "🔵","#E6F1FB",f"{k} moved to In Progress",f"{summ} — picked up by {ev['author']}"
            else:
                icon,bg,title,desc = "🔄","#F4F5F7",f"{k} status → {ev['to']}",f"{summ} — {ev['author']}"
        elif t == "priority":
            if ev["to"].lower() in ("p0","critical","highest"):
                icon,bg,title,desc = "🚨","#FFF5F5",f"{k} escalated to {ev['to']}",f"{summ} — raised from {ev['from']} by {ev['author']}"
            else:
                icon,bg,title,desc = "⚠️","#FFFAF0",f"{k} priority → {ev['to']}",f"{summ} — changed by {ev['author']}"
        elif t == "comment":
            icon,bg,title,desc = "💬","#E6F1FB",f"Update on {k}",f"{ev['text']} — {ev['author']}"
        elif t == "created":
            icon,bg,title,desc = "🎫","#F4F5F7",f"{k} opened",summ
            seen_keys.add(k)
        else:
            continue

        timeline.append(
            f'<div class="tl-item">'
            f'<div class="tl-ic" style="background:{bg}">{icon}</div>'
            f'<div class="tl-content">'
            f'<div class="tl-t"><a class="tlink" href="{url}" target="_blank">{k}</a> — {title}</div>'
            f'<div class="tl-d">{desc}</div>'
            f'<div class="tl-dt">{ts_fmt}</div>'
            f'</div></div>'
        )
        if len(timeline) >= limit:
            break

    return "\n".join(timeline) if timeline else '<p style="padding:1rem;font-size:12px;color:#5E6C84">No recent activity found.</p>'

def compute_health(p0p1, open_tickets, features, resolved):
    score = 10
    if   len(p0p1) >= 3: score -= 4
    elif len(p0p1) == 2: score -= 3
    elif len(p0p1) == 1: score -= 2
    if   len(open_tickets) >= 10: score -= 2
    elif len(open_tickets) >= 6:  score -= 1
    pending = len([i for i in open_tickets if 'pending' in (i['fields'].get('status',{}).get('name','') or '').lower()])
    if   pending >= 4: score -= 2
    elif pending >= 2: score -= 1
    if len(features) >= 5: score -= 1
    if len(resolved) == 0: score -= 1
    score = max(1, min(10, score))
    label = "Healthy" if score >= 8 else "Stable" if score >= 6 else "Needs Attention" if score >= 4 else "At Risk"
    color = "#68D391" if score >= 8 else "#FFC107" if score >= 6 else "#FC8181"
    return score, label, color

def build_citizens_html(p0p1, open_tickets, features, resolved, timeline_html):
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    score, health_label, health_color = compute_health(p0p1, open_tickets, features, resolved)
    pending = len([i for i in open_tickets if 'pending' in (i['fields'].get('status',{}).get('name','') or '').lower()])
    p0_keys  = [i["key"] for i in p0p1[:3]]
    high_keys= [i["key"] for i in open_tickets if (i['fields'].get('priority',{}).get('name','') or '').lower() in ('high','p1','highest')][:3]

    p0_rows = "".join(ticket_row(i) for i in p0p1[:5]) or \
        '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No active P0/P1 incidents</td></tr>'
    tk_rows = "".join(ticket_row(i) for i in open_tickets[:10]) or \
        '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No open tickets</td></tr>'

    feat_items = ""
    for i in features[:5]:
        key  = i["key"]
        summ = (i["fields"].get("summary") or "")[:65]
        url  = f"{JIRA_BASE}/browse/{key}"
        sc_, sl = status_class(i["fields"].get("status",{}).get("name",""))
        feat_items += f'<div class="fr-item"><div class="fr-icon" style="background:#E6F1FB">💡</div><div class="fr-content"><div class="fr-title">{summ}</div><div class="fr-meta"><a class="tlink" href="{url}" target="_blank">{key}</a></div></div><span class="fr-status {sc_}">{sl}</span></div>'

    data_js = json.dumps({
        "p0p1": len(p0p1), "open": len(open_tickets),
        "features": len(features), "resolved": len(resolved),
        "pendingEng": pending, "p0keys": p0_keys,
        "highKeys": high_keys, "generated": now
    })

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Citizens Bank — Customer Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
body{{background:#F4F5F7}}
.nav{{background:#0B1F45;padding:0 1.5rem;height:42px;display:flex;align-items:center;justify-content:space-between}}
.nav-links{{display:flex;gap:1.5rem}}
.nl{{font-size:12px;font-weight:500;color:rgba(255,255,255,0.45);text-decoration:none;padding-bottom:2px;border-bottom:2px solid transparent}}
.nl.active{{color:#fff;border-color:#00C2E0}}
.nav-back{{font-size:11px;color:#00C2E0;text-decoration:none}}
.hero{{background:#0B1F45;padding:1.1rem 1.5rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;border-bottom:1px solid #122752}}
.hero-left{{display:flex;align-items:center;gap:10px}}
.logo{{width:42px;height:42px;background:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:#0B1F45}}
.hero-name{{font-size:18px;font-weight:700;color:#fff}}
.hero-meta{{font-size:11px;color:rgba(255,255,255,0.5);margin-top:2px}}
.hbadge{{padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15)}}
.hdot{{width:7px;height:7px;border-radius:50%}}
.body{{padding:1.25rem 1.5rem}}
.metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:1.25rem}}
.metric{{background:#fff;border-radius:8px;padding:.9rem 1rem;border:.5px solid #DFE1E6}}
.mlabel{{font-size:10px;color:#5E6C84;font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}}
.mval{{font-size:24px;font-weight:700;line-height:1;margin-bottom:3px}}
.msub{{font-size:10px;color:#5E6C84}}
.red{{color:#E53E3E}}.orange{{color:#DD6B20}}.yellow{{color:#D69E2E}}.green{{color:#38A169}}.blue{{color:#1A6FDB}}
.grid2{{display:grid;grid-template-columns:1fr 280px;gap:1rem;align-items:start}}
.sec{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1rem}}
.sec-head{{padding:.7rem 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:center;gap:8px}}
.sec-title{{font-size:12px;font-weight:700;color:#172B4D}}
.badge{{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600}}
.br{{background:#FFF5F5;color:#A32D2D}}.bo{{background:#FFFAF0;color:#854F0B}}.bb{{background:#E6F1FB;color:#0C447C}}.bg{{background:#EAF3DE;color:#27500A}}
table{{width:100%;border-collapse:collapse;font-size:11px}}
th{{font-size:10px;font-weight:600;color:#5E6C84;padding:6px 1.1rem;text-align:left;background:#FAFBFC;border-bottom:.5px solid #DFE1E6;text-transform:uppercase;letter-spacing:.04em}}
td{{padding:7px 1.1rem;border-bottom:.5px solid #DFE1E6;color:#172B4D;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
.tlink{{color:#1A6FDB;text-decoration:none;font-weight:700;font-size:11px}}
.pb{{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px}}
.pc{{background:#E53E3E;color:#fff}}.ph{{background:#FFF5F5;color:#A32D2D}}.pm{{background:#FFFAF0;color:#854F0B}}.pl{{background:#F4F5F7;color:#5E6C84}}
.sp{{font-size:10px;font-weight:600;padding:2px 7px;border-radius:10px}}
.so{{background:#FFF5F5;color:#A32D2D}}.si{{background:#E6F1FB;color:#0C447C}}.spe{{background:#FFFAF0;color:#854F0B}}.sc{{background:#EAF3DE;color:#27500A}}
.ai-panel{{background:#0B1F45;border-radius:10px;padding:1.1rem;margin-bottom:1rem}}
.ai-eyebrow{{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#00C2E0;margin-bottom:3px}}
.ai-title{{font-size:13px;font-weight:700;color:#fff;margin-bottom:8px}}
.ai-body{{font-size:11px;color:rgba(255,255,255,0.75);line-height:1.7}}
.ai-footer{{margin-top:8px;padding-top:8px;border-top:.5px solid rgba(255,255,255,0.1);display:flex;align-items:center;justify-content:space-between}}
.ai-score-label{{font-size:10px;color:rgba(255,255,255,0.4)}}
.ai-score-val{{font-size:22px;font-weight:800}}
.ai-score-max{{font-size:11px;color:rgba(255,255,255,0.3)}}
.ai-ts{{font-size:10px;color:rgba(255,255,255,0.3)}}
.sb-sec{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1rem}}
.sb-head{{padding:.7rem 1rem;border-bottom:.5px solid #DFE1E6;font-size:12px;font-weight:700;color:#172B4D}}
.ir{{display:flex;align-items:center;justify-content:space-between;padding:7px 1rem;border-bottom:.5px solid #DFE1E6}}
.ir:last-child{{border-bottom:none}}
.ilabel{{font-size:11px;color:#5E6C84}}.ival{{font-size:11px;font-weight:600;color:#172B4D}}
.bar-row{{display:flex;align-items:center;gap:6px;padding:4px 1rem}}
.blabel{{font-size:10px;color:#5E6C84;width:60px;flex-shrink:0}}
.btrack{{flex:1;height:7px;background:#F4F5F7;border-radius:4px;overflow:hidden}}
.bfill{{height:100%;border-radius:4px}}
.bval{{font-size:10px;font-weight:700;width:16px;text-align:right}}
.pulse-row{{padding:7px 1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:flex-start;gap:7px}}
.pulse-row:last-child{{border-bottom:none}}
.pdot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:3px}}
.ptext{{font-size:11px;color:#5E6C84;line-height:1.4}}
.ptext b{{color:#172B4D}}
.fr-item{{padding:9px 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:flex-start;gap:8px}}
.fr-item:last-child{{border-bottom:none}}
.fr-icon{{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;margin-top:1px}}
.fr-content{{flex:1}}
.fr-title{{font-size:12px;font-weight:600;color:#172B4D;margin-bottom:2px}}
.fr-meta{{font-size:11px;color:#5E6C84}}
.fr-status{{font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600;flex-shrink:0;margin-top:2px}}
.tl{{padding:1rem 1.1rem}}
.tl-item{{display:flex;gap:10px;padding-bottom:1rem;position:relative}}
.tl-item::before{{content:'';position:absolute;left:13px;top:26px;bottom:0;width:1px;background:#DFE1E6}}
.tl-item:last-child::before{{display:none}}
.tl-ic{{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0;z-index:1}}
.tl-content{{flex:1}}
.tl-t{{font-size:11px;font-weight:700;color:#172B4D;margin-bottom:2px}}
.tl-d{{font-size:10px;color:#5E6C84;line-height:1.5}}
.tl-dt{{font-size:10px;color:#A0AEC0;margin-top:2px}}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span>
    <span class="nl active">Customers</span>
    <span class="nl">Incidents</span>
    <span class="nl">Onboarding</span>
  </div>
  <a class="nav-back" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/1990557712/Customer+Portfolio" target="_parent">← All Customers</a>
</div>
<div class="hero">
  <div class="hero-left">
    <div class="logo">CB</div>
    <div>
      <div class="hero-name">Citizens Bank, N.A.</div>
      <div class="hero-meta">AWS · us-east-1 · Oracle &amp; MySQL &amp; PostgreSQL · Production</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <div class="hbadge"><div class="hdot" id="health-dot" style="background:{health_color}"></div><span id="health-badge" style="color:{health_color}">{health_label}</span></div>
    <span style="font-size:10px;color:rgba(255,255,255,0.3)">Refreshed: {now}</span>
  </div>
</div>
<div class="body">
  <div class="metrics">
    <div class="metric"><div class="mlabel">Open P0/P1</div><div class="mval {'red' if len(p0p1)>0 else 'green'}">{len(p0p1)}</div><div class="msub">Active critical issues</div></div>
    <div class="metric"><div class="mlabel">Open Tickets</div><div class="mval {'orange' if len(open_tickets)>5 else 'yellow'}">{len(open_tickets)}</div><div class="msub">Across all priorities</div></div>
    <div class="metric"><div class="mlabel">Feature Requests</div><div class="mval blue">{len(features)}</div><div class="msub">Pending delivery</div></div>
    <div class="metric"><div class="mlabel">Resolved (30d)</div><div class="mval green">{len(resolved)}</div><div class="msub">Last 30 days</div></div>
    <div class="metric"><div class="mlabel">Health Score</div><div class="mval" id="m-score" style="color:{health_color}">{score}/10</div><div class="msub">Rule-based</div></div>
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
        <div class="sec-head"><span class="sec-title">🎫 Open Support Tickets</span><span class="badge bo">{len(open_tickets)} Open</span></div>
        <table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{tk_rows}</tbody></table>
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">💡 Feature Requests</span><span class="badge bb">{len(features)} Active</span></div>
        {feat_items or '<p style="padding:1rem;font-size:12px;color:#5E6C84">No open feature requests.</p>'}
      </div>
      <div class="sec">
        <div class="sec-head"><span class="sec-title">📅 Recent Activity</span><span class="badge bg">Live</span></div>
        <div class="tl">{timeline_html}</div>
      </div>
    </div>
    <div>
      <div class="sb-sec">
        <div class="sb-head">🏢 Account Details</div>
        <div class="ir"><span class="ilabel">Account</span><span class="ival">Citizens Bank, N.A.</span></div>
        <div class="ir"><span class="ilabel">CSE Owner</span><span class="ival">Vinod</span></div>
        <div class="ir"><span class="ilabel">TAM / TPM</span><span class="ival">Kamal</span></div>
        <div class="ir"><span class="ilabel">Cloud</span><span class="ival">AWS us-east-1</span></div>
        <div class="ir"><span class="ilabel">Engines</span><span class="ival">Oracle · MySQL · PG</span></div>
        <div class="ir"><span class="ilabel">Phase</span><span class="ival">🟠 Stabilisation</span></div>
        <div class="ir"><span class="ilabel">Portal</span><span class="ival"><a class="tlink" href="https://citizens.tessell.com" target="_blank">citizens.tessell.com</a></span></div>
      </div>
      <div class="sb-sec">
        <div class="sb-head">📊 Ticket Volume (6 months)</div>
        <div style="padding:8px 0 4px">
          <div class="bar-row"><span class="blabel">Oct 2025</span><div class="btrack"><div class="bfill" style="width:38%;background:#38A169"></div></div><span class="bval green">3</span></div>
          <div class="bar-row"><span class="blabel">Nov 2025</span><div class="btrack"><div class="bfill" style="width:63%;background:#D69E2E"></div></div><span class="bval yellow">5</span></div>
          <div class="bar-row"><span class="blabel">Dec 2025</span><div class="btrack"><div class="bfill" style="width:88%;background:#DD6B20"></div></div><span class="bval orange">7</span></div>
          <div class="bar-row"><span class="blabel">Jan 2026</span><div class="btrack"><div class="bfill" style="width:75%;background:#DD6B20"></div></div><span class="bval orange">6</span></div>
          <div class="bar-row"><span class="blabel">Feb 2026</span><div class="btrack"><div class="bfill" style="width:75%;background:#DD6B20"></div></div><span class="bval orange">6</span></div>
          <div class="bar-row"><span class="blabel">Mar 2026</span><div class="btrack"><div class="bfill" style="width:100%;background:#E53E3E"></div></div><span class="bval red">8</span></div>
        </div>
      </div>
      <div class="sb-sec">
        <div class="sb-head">💬 Customer Pulse</div>
        <div class="pulse-row"><div class="pdot" style="background:#E53E3E"></div><div class="ptext"><b>Frustrated</b> — clone to QA blocked</div></div>
        <div class="pulse-row"><div class="pdot" style="background:#DD6B20"></div><div class="ptext"><b>Concerned</b> — Perf Insights dark since Nov 2025</div></div>
        <div class="pulse-row"><div class="pdot" style="background:#DD6B20"></div><div class="ptext"><b>Concerned</b> — MySQL ZZ6 HA recurring</div></div>
        <div class="pulse-row"><div class="pdot" style="background:#D69E2E"></div><div class="ptext"><b>Waiting</b> — billing download pending eng</div></div>
        <div class="pulse-row"><div class="pdot" style="background:#38A169"></div><div class="ptext"><b>Positive</b> — DB upgrade to 7.64.1 smooth</div></div>
      </div>
      <div class="sb-sec">
        <div class="sb-head">🔗 Quick Links</div>
        <div class="ir"><a class="tlink" href="{JIRA_BASE}/issues/?jql=text+~+%22Citizens%22+AND+statusCategory+!%3D+Done" target="_blank">All Open Citizens Tickets</a></div>
        <div class="ir"><a class="tlink" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/1990557712" target="_blank">Customer Portfolio</a></div>
        <div class="ir"><a class="tlink" href="https://citizens.tessell.com" target="_blank">Citizens Tessell Portal</a></div>
      </div>
    </div>
  </div>
</div>
<script>
const DATA = {data_js};
function runHealth() {{
  const el = document.getElementById('ai-body');
  const sc = document.getElementById('ai-score');
  let score = 10, findings = [], actions = [];
  if (DATA.p0p1 >= 3)      {{ score-=4; findings.push(`<b style="color:#FC8181">${{DATA.p0p1}} active P0 incidents</b> (${{DATA.p0keys.join(', ')}})`); actions.push(`Escalate ${{DATA.p0keys[0]}} to engineering leadership for same-day resolution`); }}
  else if (DATA.p0p1 === 2) {{ score-=3; findings.push(`<b style="color:#FC8181">2 active P0 incidents</b> blocking operations (${{DATA.p0keys.join(', ')}})`); actions.push(`Escalate ${{DATA.p0keys[0]}} and ${{DATA.p0keys[1]}} — both need engineering owner today`); }}
  else if (DATA.p0p1 === 1) {{ score-=2; findings.push(`<b style="color:#FFC107">1 active P0/P1</b> open (${{DATA.p0keys[0]}})`); actions.push(`Ensure ${{DATA.p0keys[0]}} has daily updates to customer`); }}
  else                       {{ findings.push('<b style="color:#68D391">No active P0/P1 incidents</b>'); }}
  if (DATA.open >= 8)        {{ score-=2; findings.push(`High backlog: <b>${{DATA.open}} tickets</b> open`); }}
  else if (DATA.open >= 5)   {{ score-=1; findings.push(`Moderate backlog: <b>${{DATA.open}} open tickets</b>`); }}
  else                       {{ findings.push(`<b style="color:#68D391">Healthy ticket volume</b>: ${{DATA.open}} open`); }}
  if (DATA.pendingEng >= 4)  {{ score-=2; findings.push(`<b>${{DATA.pendingEng}} tickets stuck pending engineering</b>`); actions.push(`Review ${{DATA.pendingEng}} blocked tickets and set ETAs for customer`); }}
  else if (DATA.pendingEng >= 2) {{ score-=1; findings.push(`${{DATA.pendingEng}} tickets pending engineering`); }}
  if (DATA.features >= 5)    {{ score-=1; findings.push(`Large feature backlog: <b>${{DATA.features}} requests</b>`); actions.push('Schedule a feature roadmap call to set delivery expectations'); }}
  if (DATA.resolved === 0)   {{ score-=1; findings.push('<b style="color:#FFC107">No tickets resolved in 30 days</b>'); }}
  else                       {{ findings.push(`<b style="color:#68D391">${{DATA.resolved}} resolved</b> in last 30 days`); }}
  score = Math.max(1, Math.min(10, score));
  const color = score>=8?'#68D391':score>=6?'#FFC107':'#FC8181';
  const label = score>=8?'Healthy':score>=6?'Stable':score>=4?'Needs Attention':'At Risk';
  document.getElementById('health-badge').textContent = label;
  document.getElementById('health-badge').style.color = color;
  document.getElementById('health-dot').style.background = color;
  let html = findings.map(f=>`<p style="margin-bottom:6px">• ${{f}}</p>`).join('');
  if (actions.length) html += `<div style="margin-top:8px;padding-top:8px;border-top:.5px solid rgba(255,255,255,0.1)"><p style="font-size:10px;font-weight:700;color:#00C2E0;letter-spacing:.08em;text-transform:uppercase;margin-bottom:5px">Recommended Actions</p>${{actions.map(a=>`<p style="margin-bottom:4px">→ ${{a}}</p>`).join('')}}</div>`;
  el.innerHTML = html;
  sc.textContent = score;
  sc.style.color = color;
  document.getElementById('ai-ts').textContent = 'Assessed: ' + DATA.generated;
}}
window.onload = runHealth;
</script>
</body>
</html>"""

def build_master_html(customers):
    now = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    total     = len([c for c in customers if c.get("name")])
    at_risk   = len([c for c in customers if c.get("health") == "atrisk"])
    attention = len([c for c in customers if c.get("health") == "attention"])
    healthy   = len([c for c in customers if c.get("health") in ("healthy","stable")])
    total_p0  = sum(c.get("p0",0) for c in customers if c.get("name"))

    cards = ""
    for c in customers:
        if not c.get("name"):
            cards += '<div class="placeholder-card" data-health="placeholder"><div class="placeholder-icon">🏢</div><div>Customer page coming soon</div></div>'
            continue
        hc    = c["health"]
        hl    = c["healthLabel"]
        hcol  = "#68D391" if hc in ("healthy","stable") else "#FFC107" if hc=="attention" else "#FC8181"
        p0col = "red" if c["p0"]>0 else "green"
        tkcol = "orange" if c["openTickets"]>5 else "gray" if c["openTickets"]>2 else "green"
        tags  = "".join(f'<span class="tag">{e}</span>' for e in c["engines"]) + f'<span class="tag">{c["cloud"]}</span>'
        url   = c.get("dashboardUrl","#")
        cards += f"""<a class="cust-card" data-health="{hc}" data-name="{c['name'].lower()}" href="{url}" target="_parent" style="text-decoration:none">
  <div class="card-header">
    <div class="card-logo" style="background:{c['logoBg']};color:{c['logoColor']}">{c['initials']}</div>
    <div><div class="card-name">{c['name']}</div><div class="card-meta">{c['region']} · CSE: {c.get('cseOwner','—')}</div></div>
    <div class="health-pill" style="background:{hcol}1A;border:1px solid {hcol}4D;color:{hcol}"><div class="hp-dot" style="background:{hcol}"></div>{hl}</div>
  </div>
  <div class="card-body">
    <div class="card-stats">
      <div class="cs"><div class="cs-val {p0col}">{c['p0']}</div><div class="cs-label">P0/P1</div></div>
      <div class="cs"><div class="cs-val {tkcol}">{c['openTickets']}</div><div class="cs-label">Open</div></div>
      <div class="cs"><div class="cs-val blue">{c['features']}</div><div class="cs-label">Features</div></div>
    </div>
    <div class="card-tags">{tags}</div>
    <div class="card-footer"><span class="phase-label">{c['phase']}</span><span class="drill-btn">View Dashboard →</span></div>
  </div>
</a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CSE — Customer Portfolio</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
body{{background:#F4F5F7}}
.nav{{background:#0B1F45;padding:0 1.5rem;height:42px;display:flex;align-items:center;justify-content:space-between}}
.nav-links{{display:flex;gap:1.5rem}}
.nl{{font-size:12px;font-weight:500;color:rgba(255,255,255,0.45);text-decoration:none;padding-bottom:2px;border-bottom:2px solid transparent}}
.nl.active{{color:#fff;border-color:#00C2E0}}
.status-badge{{display:flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:#7DDBA3;background:rgba(125,219,163,0.12);padding:3px 9px;border-radius:20px;border:.5px solid rgba(125,219,163,0.25)}}
.sdot{{width:6px;height:6px;border-radius:50%;background:#7DDBA3}}
.hero{{background:#0B1F45;padding:1.25rem 1.5rem 1.5rem;border-bottom:1px solid #122752}}
.hero-top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:1rem}}
.hero-title{{font-size:20px;font-weight:700;color:#fff}}
.hero-sub{{font-size:12px;color:rgba(255,255,255,0.45);margin-top:2px}}
.refresh-info{{font-size:10px;color:rgba(255,255,255,0.3)}}
.port-metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}
.pm{{background:rgba(255,255,255,0.05);border:.5px solid rgba(255,255,255,0.1);border-radius:8px;padding:.8rem 1rem}}
.pm-label{{font-size:10px;color:rgba(255,255,255,0.4);font-weight:500;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}}
.pm-val{{font-size:22px;font-weight:700;color:#fff;line-height:1}}
.pm-sub{{font-size:10px;margin-top:3px}}
.body{{padding:1.25rem 1.5rem}}
.filter-bar{{display:flex;align-items:center;gap:8px;margin-bottom:1.1rem;flex-wrap:wrap}}
.filter-btn{{font-size:11px;font-weight:500;padding:4px 12px;border-radius:20px;border:.5px solid #DFE1E6;background:#fff;color:#5E6C84;cursor:pointer}}
.filter-btn.active{{background:#0B1F45;color:#fff;border-color:#0B1F45}}
.search-input{{flex:1;max-width:240px;padding:5px 12px;border-radius:20px;border:.5px solid #DFE1E6;font-size:12px;outline:none;background:#fff;color:#172B4D}}
.cards-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.cust-card{{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;cursor:pointer;transition:transform .15s}}
.cust-card:hover{{transform:translateY(-2px)}}
.card-header{{padding:1rem 1.1rem .8rem;border-bottom:.5px solid #F4F5F7;display:flex;align-items:center;gap:10px}}
.card-logo{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;flex-shrink:0}}
.card-name{{font-size:13px;font-weight:700;color:#172B4D;margin-bottom:1px}}
.card-meta{{font-size:10px;color:#5E6C84}}
.health-pill{{margin-left:auto;padding:3px 9px;border-radius:20px;font-size:10px;font-weight:700;display:flex;align-items:center;gap:4px;flex-shrink:0}}
.hp-dot{{width:6px;height:6px;border-radius:50%}}
.card-body{{padding:.8rem 1.1rem}}
.card-stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:.8rem}}
.cs{{text-align:center}}
.cs-val{{font-size:18px;font-weight:700;line-height:1}}
.cs-label{{font-size:10px;color:#5E6C84;margin-top:2px}}
.card-tags{{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:.8rem}}
.tag{{font-size:10px;padding:2px 7px;border-radius:4px;background:#F4F5F7;color:#5E6C84;font-weight:500}}
.card-footer{{display:flex;align-items:center;justify-content:space-between;padding-top:.7rem;border-top:.5px solid #F4F5F7}}
.phase-label{{font-size:10px;font-weight:600;color:#5E6C84}}
.drill-btn{{font-size:11px;font-weight:600;color:#1A6FDB}}
.placeholder-card{{background:#FAFBFC;border:.5px dashed #DFE1E6;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:180px;color:#A0AEC0;font-size:12px;gap:6px}}
.placeholder-icon{{font-size:24px;opacity:.4}}
.red{{color:#E53E3E}}.orange{{color:#DD6B20}}.green{{color:#38A169}}.blue{{color:#1A6FDB}}.gray{{color:#5E6C84}}
</style>
</head>
<body>
<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span>
    <span class="nl active">Customers</span>
    <span class="nl">Incidents</span>
    <span class="nl">Onboarding</span>
  </div>
  <div class="status-badge"><div class="sdot"></div>All systems operational</div>
</div>
<div class="hero">
  <div class="hero-top">
    <div><div class="hero-title">Customer Portfolio</div><div class="hero-sub">CSE · Active customer health &amp; implementation status</div></div>
    <span class="refresh-info">Refreshed: {now}</span>
  </div>
  <div class="port-metrics">
    <div class="pm"><div class="pm-label">Total Customers</div><div class="pm-val">{total}</div><div class="pm-sub" style="color:rgba(255,255,255,0.4)">Active accounts</div></div>
    <div class="pm"><div class="pm-label">At Risk</div><div class="pm-val" style="color:#FC8181">{at_risk}</div><div class="pm-sub" style="color:#FC8181">Needs immediate action</div></div>
    <div class="pm"><div class="pm-label">Open P0/P1</div><div class="pm-val" style="color:#FC8181">{total_p0}</div><div class="pm-sub" style="color:rgba(255,255,255,0.4)">Critical incidents</div></div>
    <div class="pm"><div class="pm-label">Needs Attention</div><div class="pm-val" style="color:#FFC107">{attention}</div><div class="pm-sub" style="color:rgba(255,255,255,0.4)">Monitoring required</div></div>
    <div class="pm"><div class="pm-label">Healthy</div><div class="pm-val" style="color:#68D391">{healthy}</div><div class="pm-sub" style="color:rgba(255,255,255,0.4)">Stable accounts</div></div>
  </div>
</div>
<div class="body">
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterCards('all',this)">All</button>
    <button class="filter-btn" onclick="filterCards('atrisk',this)">At Risk</button>
    <button class="filter-btn" onclick="filterCards('attention',this)">Needs Attention</button>
    <button class="filter-btn" onclick="filterCards('healthy',this)">Healthy</button>
    <button class="filter-btn" onclick="filterCards('stable',this)">Stable</button>
    <input class="search-input" type="text" placeholder="Search customers..." oninput="searchCards(this.value)"/>
  </div>
  <div class="cards-grid">{cards}</div>
</div>
<script>
function filterCards(h,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.cust-card,[data-health]').forEach(el=>{{
    el.style.display = h==='all'||el.dataset.health===h?'':'none';
  }});
}}
function searchCards(q){{
  q=q.toLowerCase();
  document.querySelectorAll('.cust-card').forEach(el=>{{
    el.style.display=(el.dataset.name||'').includes(q)?'':'none';
  }});
}}
</script>
</body>
</html>"""

if __name__ == "__main__":
    print("Fetching Jira data for Citizens Bank...")
    p0p1          = jql(JQL_P0P1,           max=10)
    open_tkts     = jql(JQL_OPEN,           max=20)
    features      = jql(JQL_FEATURES,       max=10)
    resolved      = jql(JQL_RESOLVED_30D,   max=50)
    recent_issues = jql(JQL_RECENT_UPDATED, max=12)

    print(f"  P0/P1:{len(p0p1)}  Open:{len(open_tkts)}  Features:{len(features)}  Resolved(30d):{len(resolved)}  Recent:{len(recent_issues)}")

    print("Building activity timeline...")
    timeline_html = build_timeline(recent_issues, limit=8)

    print("Building Citizens Bank dashboard...")
    citizens_html = build_citizens_html(p0p1, open_tkts, features, resolved, timeline_html)
    with open("citizens_bank_dashboard.html", "w") as f:
        f.write(citizens_html)

    # Compute health score for master dashboard
    score, health_label, health_color = compute_health(p0p1, open_tkts, features, resolved)

    print("Building master dashboard...")
    customers = [
        {
            "name": "Citizens Bank, N.A.", "initials": "CB",
            "logoColor": "#0B1F45", "logoBg": "#E6F1FB",
            "cloud": "AWS", "region": "us-east-1",
            "engines": ["Oracle","MySQL","PostgreSQL"],
            "phase": "🟠 Stabilisation",
            "health": "atrisk" if score <= 4 else "attention" if score <= 6 else "stable",
            "healthLabel": health_label,
            "p0": len(p0p1), "openTickets": len(open_tkts), "features": len(features),
            "cseOwner": "Vinod",
            "dashboardUrl": "https://tessell.atlassian.net/wiki/spaces/CSE/pages/2164948993/Citizens+Bank+Customer+Dashboard"
        },
        {
            "name": "Atlas Air", "initials": "AA",
            "logoColor": "#0F5C8A", "logoBg": "#E6F1FB",
            "cloud": "AWS", "region": "us-east-1",
            "engines": ["Oracle"], "phase": "🟢 Production",
            "health": "stable", "healthLabel": "Stable",
            "p0": 0, "openTickets": 2, "features": 1,
            "cseOwner": "Vinod", "dashboardUrl": "#"
        },
        {
            "name": "Aon", "initials": "Aon",
            "logoColor": "#7B2FBE", "logoBg": "#EEEDFE",
            "cloud": "Azure", "region": "eastus",
            "engines": ["Oracle"], "phase": "⚫ Steady State",
            "health": "healthy", "healthLabel": "Healthy",
            "p0": 0, "openTickets": 1, "features": 2,
            "cseOwner": "", "dashboardUrl": "#"
        },
        {"name": None}, {"name": None}, {"name": None}
    ]
    master_html = build_master_html(customers)
    with open("master_dashboard.html", "w") as f:
        f.write(master_html)

    print("Done — citizens_bank_dashboard.html and master_dashboard.html written.")
