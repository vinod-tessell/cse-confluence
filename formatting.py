"""
formatting.py — date helpers, ticket row renderer, health score computation,
                and the recent activity timeline builder.
"""
from datetime import datetime

import requests

from config import JIRA_BASE, EST, auth, headers


# ── Date / age helpers ────────────────────────────────────────────────────────

def fmt_date(iso):
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso[:10]).strftime("%b %d, %Y")
    except Exception:
        return iso[:10]


def age_days(iso):
    if not iso:
        return "—"
    try:
        d = (datetime.now(EST) - datetime.fromisoformat(iso[:19]).replace(tzinfo=EST)).days
        return f"{d}d" if d > 0 else "today"
    except Exception:
        return "—"


# ── Priority / status CSS helpers ─────────────────────────────────────────────

def sre_priority(fields):
    labels = [l.upper() for l in (fields.get("labels") or [])]
    if "P0" in labels: return "pc", "P0"
    if "P1" in labels: return "ph", "P1"
    return None, None


def priority_class(p):
    p = (p or "").lower()
    if p in ("highest", "critical"): return "pc", "Highest"
    if p in ("high",):               return "ph", "High"
    if p in ("medium",):             return "pm", "Medium"
    return "pl", p.capitalize() or "—"


def status_class(s):
    s = (s or "").lower()
    if "progress" in s or "review"   in s: return "si",  "In Progress"
    if "pending"  in s or "wait"     in s: return "spe", "Pending Eng"
    if "done"     in s or "closed"   in s or "resolved" in s: return "sc", "Closed"
    return "so", s.capitalize() or "Open"


# ── Ticket row HTML ───────────────────────────────────────────────────────────

def ticket_row(issue):
    key  = issue["key"]
    f    = issue["fields"]
    summ = (f.get("summary") or "")[:72]
    sre_pc, sre_pl = sre_priority(f)
    pc, pl  = (sre_pc, sre_pl) if sre_pc else priority_class(f.get("priority", {}).get("name", ""))
    sc_, sl = status_class(f.get("status", {}).get("name", ""))
    url = f"{JIRA_BASE}/browse/{key}"
    return (
        f'<tr><td><a class="tlink" href="{url}" target="_blank">{key}</a></td>'
        f'<td>{summ}</td>'
        f'<td><span class="pb {pc}">{pl}</span></td>'
        f'<td><span class="sp {sc_}">{sl}</span></td>'
        f'<td>{age_days(f.get("created", ""))}</td></tr>'
    )


# ── Health score ──────────────────────────────────────────────────────────────

def compute_health(p0p1, support_tickets, features, resolved, eng_tickets):
    """
    Score from 10, deductions:
      P0/P1 incidents:        −2 / −3 / −4
      SR support backlog:     −1 / −2
      Pending eng on SR:      −1 / −2
      TS eng backlog ≥5:      −1
      TS feature backlog ≥5:  −1
      0 SR resolved in 30d:   −1
    Floor: 1.  Returns (score, label, hex_color, health_key, pending_count).
    """
    score   = 10
    pending = len([
        i for i in support_tickets
        if 'pending' in (i['fields'].get('status', {}).get('name', '') or '').lower()
    ])

    if   len(p0p1) >= 3:             score -= 4
    elif len(p0p1) == 2:             score -= 3
    elif len(p0p1) == 1:             score -= 2

    if   len(support_tickets) >= 10: score -= 2
    elif len(support_tickets) >= 6:  score -= 1

    if   pending >= 4:               score -= 2
    elif pending >= 2:               score -= 1

    if   len(eng_tickets) >= 5:      score -= 1
    if   len(features) >= 5:         score -= 1
    if   len(resolved) == 0:         score -= 1

    score = max(1, min(10, score))
    label = ("Healthy"         if score >= 8 else
             "Stable"          if score >= 6 else
             "Needs Attention" if score >= 4 else "At Risk")
    color = "#68D391" if score >= 8 else "#FFC107" if score >= 6 else "#FC8181"
    hk    = ("healthy"   if score >= 8 else
             "stable"    if score >= 6 else
             "attention" if score >= 4 else "atrisk")
    return score, label, color, hk, pending


# ── Timeline builder ──────────────────────────────────────────────────────────

def get_changelog(key):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/issue/{key}/changelog",
        auth=auth, headers=headers, params={"maxResults": 10},
    )
    if r.status_code != 200:
        return []
    events = []
    for h in r.json().get("values", []):
        ts     = h.get("created", "")
        author = h.get("author", {}).get("displayName", "Tessell")
        for item in h.get("items", []):
            if item.get("field", "") in ("status", "priority"):
                events.append({
                    "ts": ts, "key": key, "type": item["field"],
                    "from": item.get("fromString", "") or "",
                    "to":   item.get("toString",   "") or "",
                    "author": author,
                })
    return events


def get_comments(key, max=2):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/issue/{key}/comment",
        auth=auth, headers=headers,
        params={"maxResults": max, "orderBy": "-created"},
    )
    if r.status_code != 200:
        return []
    out = []
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
            out.append({
                "ts":     c.get("created", ""),
                "key":    key,
                "type":   "comment",
                "author": c.get("author", {}).get("displayName", "Tessell"),
                "text":   text,
            })
    return out


def build_timeline(recent_issues, limit=8):
    all_events = []
    for issue in recent_issues[:12]:
        key  = issue["key"]
        summ = (issue["fields"].get("summary") or "")[:70]
        all_events.append({"ts": issue["fields"].get("created", ""), "key": key, "type": "created", "summary": summ})
        try:
            for ev in get_changelog(key): ev["summary"] = summ; all_events.append(ev)
        except Exception: pass
        try:
            for ev in get_comments(key): ev["summary"] = summ; all_events.append(ev)
        except Exception: pass

    def sk(e):
        try:    return datetime.fromisoformat(e["ts"][:19])
        except: return datetime.min

    all_events.sort(key=sk, reverse=True)

    seen, timeline = set(), []
    for ev in all_events:
        k, t   = ev["key"], ev["type"]
        ts_fmt = fmt_date(ev.get("ts", ""))
        url    = f"{JIRA_BASE}/browse/{k}"
        summ   = ev.get("summary", "")

        if t == "created" and k in seen:
            continue
        if t == "status":
            tl = ev["to"].lower()
            if any(x in tl for x in ("done", "resolved", "closed")):
                icon, bg, title, desc = "✅", "#EAF3DE", f"{k} resolved — {summ}", f"Status → {ev['to']} by {ev['author']}"
            elif "progress" in tl:
                icon, bg, title, desc = "🔵", "#E6F1FB", f"{k} moved to In Progress", f"{summ} — picked up by {ev['author']}"
            else:
                icon, bg, title, desc = "🔄", "#F4F5F7", f"{k} status → {ev['to']}", f"{summ} — {ev['author']}"
        elif t == "priority":
            if ev["to"].lower() in ("p0", "critical", "highest"):
                icon, bg, title, desc = "🚨", "#FFF5F5", f"{k} escalated to {ev['to']}", f"{summ} — raised by {ev['author']}"
            else:
                icon, bg, title, desc = "⚠️", "#FFFAF0", f"{k} priority → {ev['to']}", f"{summ} — {ev['author']}"
        elif t == "comment":
            icon, bg, title, desc = "💬", "#E6F1FB", f"Update on {k}", f"{ev['text']} — {ev['author']}"
        elif t == "created":
            icon, bg, title, desc = "🎫", "#F4F5F7", f"{k} opened", summ
            seen.add(k)
        else:
            continue

        timeline.append(
            f'<div class="tl-item"><div class="tl-ic" style="background:{bg}">{icon}</div>'
            f'<div class="tl-content"><div class="tl-t"><a class="tlink" href="{url}" target="_blank">{k}</a> — {title}</div>'
            f'<div class="tl-d">{desc}</div><div class="tl-dt">{ts_fmt}</div></div></div>'
        )
        if len(timeline) >= limit:
            break

    return "\n".join(timeline) if timeline else \
           '<p style="padding:1rem;font-size:12px;color:#5E6C84">No recent activity found.</p>'
