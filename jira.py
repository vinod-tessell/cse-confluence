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
    _eng_reporters = (
        '557058:f58131cb-b67d-43c7-b30d-6b58d40bd077,'
        '712020:569ba7d2-5644-4040-b7ec-b984474cdc6e,'
        '637b00bc9341d1f13604f140,'
        '712020:46ee67dd-c0d7-490d-80b0-cd603c83dd2e,'
        '712020:3e2bfdfb-b3ec-408c-a1aa-21cb19fc0669,'
        '712020:a339dba8-745e-419d-be44-b182a67e9536,'
        '712020:a205c27e-f5a5-4f90-bdda-c991ea3e0ab8,'
        '712020:ff5ca9e1-f488-4707-8bbf-5feaed42559a,'
        '712020:b6ba7c99-d0be-44d5-b650-bcce3210b37d,'
        '712020:70e6670c-814d-4ec3-8487-cadb0ab2bf62,'
        '63e5f43b491b20ef64bdd15b,'
        '712020:d727070e-8816-43ce-80a2-8acf0dc9c10b,'
        '712020:f8dc1e59-faaa-476c-9f18-08310002a804,'
        '712020:294747b1-e4d0-4cf7-b816-fed9fe283cf1,'
        '712020:96502e4a-e268-4e30-acb9-511995241dc5,'
        '712020:f0281b29-4237-4ea0-ae67-acf3e8c6d181,'
        '712020:5e36ffe3-81f6-4f40-810c-e42161e350f7,'
        '712020:48de8606-2a4c-4dc2-a4a0-31f0b86e9b24,'
        '712020:15baf6e5-f96a-40bd-9338-31f9d73b2d8c,'
        '712020:e808166e-a6ad-4298-afcc-d88b8b6d8024,'
        '712020:fd609670-975f-4185-857b-21243f83ba90,'
        '712020:74267074-99ea-48d6-9d34-5362aa868c5a,'
        '712020:ed20bfd5-32e9-44ce-bef7-9ab53ea474e2,'
        '712020:2dc87765-31b1-4a79-8591-6cbc8b9a93db,'
        '712020:6eda01f3-f094-4f4e-86e6-749b54b5bdc3,'
        '712020:ab0af858-b79b-4bfd-b3e7-89be0b35e391,'
        '712020:a4e5b996-469f-4572-aa1f-f7704f09df33,'
        '712020:a9d23dd6-5254-4580-924e-0f3734ed2e17,'
        '712020:f7d4fcc5-f015-4d5c-a41e-99482b3ef30e,'
        '712020:44572c2a-2166-4401-9052-c7b4f1d3fd28'
    )
    return {
        "p0p1":        f'project in (TS, SR) AND text ~ "{keyword}" AND (labels = P0 OR labels = P1) AND statusCategory != Done ORDER BY created DESC',
        "support":     f'project = SR AND text ~ "{keyword}" AND statusCategory != Done ORDER BY created DESC',
        "features":    f'project = TS AND ("Customers[Labels]" IN ("{keyword}") OR text ~ "{keyword}") AND ({_feat}) AND statusCategory != Done ORDER BY created DESC',
        "eng_tickets": f'project = TS AND text ~ "{keyword}" AND issuetype = Bug AND reporter IN ({_eng_reporters}) AND created >= "2026-01-01" AND statusCategory != Done ORDER BY created DESC',
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
    """6-month SR ticket counts for the trend chart.
    open = tickets created in that calendar month (still open or closed).
    resolved = tickets resolved in that calendar month.
    Simple created/resolutiondate window — avoids complex WIP logic that returns 0.
    """
    buckets = []
    today   = date.today()
    for i in range(5, -1, -1):
        mo_off = today.month - i
        yr_off = today.year + (mo_off - 1) // 12
        mo_num = ((mo_off - 1) % 12) + 1
        first  = date(yr_off, mo_num, 1)
        last   = date(yr_off + 1, 1, 1) if mo_num == 12 else date(yr_off, mo_num + 1, 1)
        f_str, l_str = first.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d")
        try:
            ro = requests.get(f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
                params={"jql": f'project = SR AND text ~ "{keyword}" AND created >= "{f_str}" AND created < "{l_str}" ORDER BY created DESC',
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
        print(f"    {first.strftime('%b %Y')}: created={open_count} resolved={resolved_count}")
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
