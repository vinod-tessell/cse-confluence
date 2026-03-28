"""
jira.py — JQL execution, customer data fetching (tickets, history, pulse).
"""
import requests
from datetime import date

from config import JIRA_BASE, auth, headers
from formatting import age_days


# ── JQL result wrapper ────────────────────────────────────────────────────────

class JqlResult:
    """
    Wraps Jira search results to expose the real total count alongside
    the fetched issues list.  Behaves like a list for all existing callsites.
    """
    def __init__(self, issues, total):
        self.issues = issues
        self.total  = total

    def __len__(self):        return self.total        # real Jira total, not just fetched
    def __iter__(self):       return iter(self.issues)
    def __getitem__(self, s): return self.issues[s]
    def __bool__(self):       return self.total > 0


def jql(query, max=20):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": query, "maxResults": max,
                "fields": "summary,priority,status,created,resolutiondate,issuetype,labels"},
    )
    r.raise_for_status()
    body   = r.json()
    issues = body.get("issues", [])
    total  = body.get("total", len(issues))
    return JqlResult(issues, total)


# ── JQL templates ─────────────────────────────────────────────────────────────

def make_jqls(keyword):
    """Return the six named JQL queries for a customer keyword."""
    _feat   = 'issuetype in (Feature, Story) OR labels in ("FeatureRequest")'
    _nofeat = f'NOT ({_feat})'
    return {
        "p0p1":        f'project in (TS, SR) AND text ~ "{keyword}" AND (labels = P0 OR labels = P1) AND statusCategory != Done ORDER BY created DESC',
        "support":     f'project = SR AND text ~ "{keyword}" AND statusCategory != Done ORDER BY created DESC',
        "features":    f'project = TS AND ("Customers[Labels]" IN ("{keyword}") OR text ~ "{keyword}") AND ({_feat}) AND statusCategory != Done ORDER BY created DESC',
        "eng_tickets": f'project = TS AND text ~ "{keyword}" AND {_nofeat} AND statusCategory != Done ORDER BY created DESC',
        "resolved":    f'project = SR AND text ~ "{keyword}" AND statusCategory = Done AND resolutiondate >= -30d ORDER BY resolutiondate DESC',
        "recent":      f'project in (TS, SR) AND text ~ "{keyword}" AND updated >= -30d ORDER BY updated DESC',
    }


# ── Customer data fetch ───────────────────────────────────────────────────────

def fetch_customer_data(keyword):
    queries = make_jqls(keyword)
    print(f"  Support query:     {queries['support']}")
    print(f"  Eng tickets query: {queries['eng_tickets']}")
    print(f"  Features query:    {queries['features']}")
    return {
        "p0p1":           jql(queries["p0p1"],        max=100),
        "support":        jql(queries["support"],     max=200),
        "features":       jql(queries["features"],    max=100),
        "eng_tickets":    jql(queries["eng_tickets"], max=100),
        "resolved":       jql(queries["resolved"],    max=500),
        "recent":         jql(queries["recent"],      max=12),
        "ticket_history": fetch_monthly_buckets(keyword),
        "pulse":          fetch_pulse_from_comments(keyword),
        "jqls":           queries,
    }


def fetch_monthly_buckets(keyword):
    """6-month SR open/resolved counts for the trend chart."""
    buckets = []
    today   = date.today()
    for i in range(5, -1, -1):
        mo_off    = today.month - i
        yr_off    = today.year + (mo_off - 1) // 12
        mo_num    = ((mo_off - 1) % 12) + 1
        first     = date(yr_off, mo_num, 1)
        last      = date(yr_off + 1, 1, 1) if mo_num == 12 else date(yr_off, mo_num + 1, 1)
        f_str, l_str = first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
        try:
            ro = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": f'project = SR AND text ~ "{keyword}" AND created <= "{l_str}" AND (resolutiondate is EMPTY OR resolutiondate >= "{f_str}") ORDER BY created DESC',
                        "maxResults": 0, "fields": "summary"})
            open_count = ro.json().get("total", 0) if ro.status_code == 200 else 0
        except Exception:
            open_count = 0
        try:
            rr = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": f'project = SR AND text ~ "{keyword}" AND statusCategory = Done AND resolutiondate >= "{f_str}" AND resolutiondate < "{l_str}" ORDER BY resolutiondate DESC',
                        "maxResults": 0, "fields": "summary"})
            resolved_count = rr.json().get("total", 0) if rr.status_code == 200 else 0
        except Exception:
            resolved_count = 0
        buckets.append({"month": first.strftime("%b %Y"), "count": open_count, "resolved": resolved_count})
    return buckets


def fetch_pulse_from_comments(keyword):
    """Scan recent SR tickets for customer sentiment signals."""
    frustrated_kw = ["escalat","urgent","not working","still broken","days","week","unacceptable","blocking","critical","frustrated","disappointed","no progress","no update","no response","waiting","how long"]
    concerned_kw  = ["issue","problem","error","fail","broken","wrong","incorrect","unexpected","impact","affects","production"]
    positive_kw   = ["thank","resolved","fixed","working","great","smooth","appreciate","perfect","done","completed","success","good"]
    waiting_kw    = ["waiting","pending","any update","please update","eta","when","timeline","status update","follow up","followup"]
    try:
        r = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
            params={"jql": f'project = SR AND text ~ "{keyword}" AND updated >= -21d ORDER BY updated DESC',
                    "maxResults": 15, "fields": "summary,status,priority,labels,created,comment"})
        if r.status_code != 200:
            return []
        issues      = r.json().get("issues", [])
        pulse_items = []
        seen        = set()
        for issue in issues:
            f          = issue["fields"]
            key        = issue["key"]
            summ       = (f.get("summary") or "")[:55]
            status     = (f.get("status", {}).get("name") or "").lower()
            labels     = [l.upper() for l in (f.get("labels") or [])]
            ticket_age = age_days(f.get("created", ""))

            if ("P0" in labels or "P1" in labels) and "frustrated" not in seen:
                plabel = "P0" if "P0" in labels else "P1"
                pulse_items.append({"sentiment": "frustrated", "key": key, "age": ticket_age,
                    "text": summ, "snippet": f"{plabel} incident open for {ticket_age} — needs immediate attention"})
                seen.add("frustrated"); continue

            if any(x in status for x in ("pending", "wait", "hold")) and "waiting" not in seen:
                pulse_items.append({"sentiment": "waiting", "key": key, "age": ticket_age,
                    "text": summ, "snippet": "Awaiting engineering response"})
                seen.add("waiting"); continue

            for c in reversed(f.get("comment", {}).get("comments", [])):
                if "tessell" in (c.get("author", {}).get("emailAddress") or "").lower():
                    continue
                author = c.get("author", {}).get("displayName", "Customer")
                body   = c.get("body", {})
                text   = ""
                if isinstance(body, dict):
                    for block in body.get("content", []):
                        for inline in block.get("content", []):
                            if inline.get("type") == "text":
                                text += inline.get("text", "") + " "
                elif isinstance(body, str):
                    text = body
                text    = text.strip()
                snippet = (text[:80] + "…") if len(text) > 80 else text
                tl      = text.lower()
                for kws, sent in [(frustrated_kw, "frustrated"), (waiting_kw, "waiting"),
                                   (positive_kw, "positive"), (concerned_kw, "concerned")]:
                    if any(k in tl for k in kws) and sent not in seen:
                        pulse_items.append({"sentiment": sent, "key": key, "age": ticket_age,
                            "text": summ, "snippet": f'"{snippet}" — {author}'})
                        seen.add(sent); break

            if len(pulse_items) >= 5:
                break

        return pulse_items[:5]
    except Exception as e:
        print(f"  ⚠️  Pulse fetch failed: {e}")
        return []
