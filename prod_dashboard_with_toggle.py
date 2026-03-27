# FULL PRODUCTION SCRIPT WITH UI DEBUG TOGGLE (MERGED)

import os, json, re, requests, hashlib
from datetime import datetime, timezone, timedelta
from requests.auth import HTTPBasicAuth

JIRA_BASE  = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_TOKEN = os.environ["JIRA_API_TOKEN"]

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
headers = {"Accept": "application/json"}

def jql(query, max=20):
    r = requests.get(
        f"{JIRA_BASE}/rest/api/3/search/jql", auth=auth, headers=headers,
        params={"jql": query, "maxResults": max,
                "fields": "summary,priority,status,created"}
    )
    r.raise_for_status()
    return r.json().get("issues", [])

def make_jqls(keyword):
    return {
        "p0p1": f'text ~ "{keyword}" AND labels in (P0,P1) AND statusCategory != Done',
        "open": f'text ~ "{keyword}" AND statusCategory != Done',
        "recent": f'text ~ "{keyword}" ORDER BY updated DESC'
    }

def fetch_customer_data(keyword):
    queries = make_jqls(keyword)
    return {
        "queries": queries,
        "p0p1": jql(queries["p0p1"]),
        "open": jql(queries["open"]),
        "recent": jql(queries["recent"]),
    }

def build_customer_html(name, data):
    queries = data.get("queries", {})

    jql_html = ""
    for name_q, query in queries.items():
        encoded = query.replace(" ", "+").replace('"', '%22')
        jira_link = f"{JIRA_BASE}/issues/?jql={encoded}"

        jql_html += f'''
        <div style="margin-bottom:10px">
            <div style="display:flex;justify-content:space-between">
                <b>{name_q}</b>
                <a href="{jira_link}" target="_blank">Run →</a>
            </div>
            <div style="font-family:monospace;font-size:11px">{query}</div>
        </div>
        '''

    return f'''
<html>
<head>
<style>
.debug-only {{ display:none; }}
.debug-enabled .debug-only {{ display:block; }}
</style>
</head>

<body>

<div style="display:flex;justify-content:space-between">
  <h2>{name}</h2>

  <div style="display:flex;align-items:center;gap:6px">
    <span style="font-size:10px">Debug</span>
    <label style="position:relative;width:34px;height:18px">
      <input type="checkbox" id="debugToggle" style="opacity:0">
      <span style="position:absolute;background:#555;top:0;left:0;right:0;bottom:0;border-radius:18px"></span>
      <span id="toggleKnob" style="position:absolute;width:14px;height:14px;left:2px;top:2px;background:white;border-radius:50%;transition:.2s"></span>
    </label>
    <span id="debugBadge" style="display:none;color:orange">DEBUG</span>
  </div>
</div>

<div>P0/P1: {len(data['p0p1'])}</div>
<div>Open: {len(data['open'])}</div>

<div class="debug-only" style="margin-top:10px">
  <h4>JQL Queries</h4>
  {jql_html}
</div>

<script>
if (localStorage.getItem("debugMode") === null) {{
  localStorage.setItem("debugMode", "false");
}}

const toggle = document.getElementById("debugToggle");
const badge = document.getElementById("debugBadge");
const knob = document.getElementById("toggleKnob");

function applyDebug(enabled) {{
  if (enabled) {{
    document.body.classList.add("debug-enabled");
    badge.style.display = "inline";
    knob.style.transform = "translateX(16px)";
  }} else {{
    document.body.classList.remove("debug-enabled");
    badge.style.display = "none";
    knob.style.transform = "translateX(0px)";
  }}
}}

const enabled = localStorage.getItem("debugMode") === "true";
toggle.checked = enabled;
applyDebug(enabled);

toggle.addEventListener("change", function() {{
  localStorage.setItem("debugMode", this.checked);
  applyDebug(this.checked);
}});
</script>

</body>
</html>
'''

if __name__ == "__main__":
    customers = ["Citizens", "Duncan", "AON"]

    for c in customers:
        data = fetch_customer_data(c)
        html = build_customer_html(c, data)

        with open(f"{c}_dashboard.html", "w") as f:
            f.write(html)

print("DONE")
