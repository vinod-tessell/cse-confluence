"""
dashboard_customer.py — builds the per-customer HTML dashboard page.

Returns a (html, js) tuple. The caller writes:
  - {slug}_dashboard.html  — the page (no inline scripts)
  - {slug}_dashboard.js    — all per-page JS, loaded via <script src>
                             This is CSP-safe in Confluence iframes.
"""
import json
from datetime import datetime

from config import JIRA_BASE, CONFLUENCE_PARENT, EST
from formatting import compute_health, ticket_row, build_timeline, status_class, age_days
from jira import make_jqls
from templates import SHARED_CSS, NAV_CUSTOMER, HEALTH_JS

def build_customer_html(cust, data):
    """Return (html_str, js_str) for the customer dashboard."""
    now         = datetime.now(EST).strftime("%b %d, %Y %H:%M EST")
    p0p1        = data["p0p1"]
    support     = data["support"]
    features    = data["features"]
    eng_tickets = data["eng_tickets"]
    resolved    = data["resolved"]
    timeline    = build_timeline(data["recent"])
    score, health_label, health_color, _, pending = compute_health(p0p1, support, features, resolved, eng_tickets)
    p0_keys   = [i["key"] for i in p0p1[:3]]
    high_keys = [i["key"] for i in support if (i['fields'].get('priority',{}).get('name','') or '').lower() in ('high','p1','highest')][:3]

    p0_rows   = "".join(ticket_row(i) for i in p0p1)   or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No active P0/P1 incidents</td></tr>'
    sup_rows  = "".join(ticket_row(i) for i in support) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No open support tickets</td></tr>'
    eng_rows  = "".join(ticket_row(i) for i in eng_tickets) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No open engineering tickets</td></tr>'

    # Truncation notes
    def _trunc_note(result, query=""):
        fetched = len(result.issues)
        total   = result.total
        if total > fetched:
            enc      = query.replace(" ", "+").replace('"', '%22')
            view_url = f"{JIRA_BASE}/issues/?jql={enc}"
            return (f'<tr><td colspan="5" style="text-align:center;padding:.6rem 1rem;'
                    f'font-size:10px;color:#854F0B;background:#FFFAF0;border-top:.5px solid #DFE1E6">'
                    f'⚠️ Showing {fetched} of {total} tickets · '
                    f'<a class="tlink" href="{view_url}" target="_blank">View all {total} in Jira →</a>'
                    f'</td></tr>')
        return ""

    _jqls     = data.get("jqls", make_jqls(cust["jql_keyword"]))
    sup_trunc  = _trunc_note(support,     _jqls.get("support",     ""))
    eng_trunc  = _trunc_note(eng_tickets, _jqls.get("eng_tickets", ""))
    p0_trunc   = _trunc_note(p0p1,        _jqls.get("p0p1",        ""))
    res_trunc  = _trunc_note(resolved,    _jqls.get("resolved",    ""))
    feat_trunc = _trunc_note(features,    _jqls.get("features",    ""))

    feat_items = ""
    for i in features:
        key = i["key"]; summ = (i["fields"].get("summary") or "")[:65]; url = f"{JIRA_BASE}/browse/{key}"
        sc_, sl = status_class(i["fields"].get("status",{}).get("name",""))
        feat_items += (f'<div class="fr-item"><div class="fr-icon" style="background:#E6F1FB">💡 </div>'
                       f'<div class="fr-content"><div class="fr-title">{summ}</div>'
                       f'<div class="fr-meta"><a class="tlink" href="{url}" target="_blank">{key}</a></div></div>'
                       f'<span class="fr-status {sc_}">{sl}</span></div>')

    portal_html = (f'<a href="{cust["portal_url"]}" target="_blank" style="color:#00C2E0;font-size:11px;text-decoration:none">{cust["portal_url"]}</a>') if cust.get("portal_url") else "—"
    engines_str = " · ".join(cust["engines"])

    tam_primary   = cust.get("tam_primary", "—")  or "—"
    tam_secondary = cust.get("tam_secondary", "")
    exec_sponsor  = cust.get("exec_sponsor", "—") or "—"
    tam_html = f'<div style="font-size:12px;font-weight:700;color:#172B4D">{tam_primary}</div>'
    if tam_secondary:
        tam_html += f'<div style="font-size:10px;color:#5E6C84;margin-top:1px">{tam_secondary} <span style="color:#DFE1E6">·</span> secondary</div>'
    hist = data.get("ticket_history", [])

    # ── Build chart JS (no inline script — written to companion .js file) ──────
    js_filename = f"{cust['id']}_dashboard.js"

    if hist:
        chart_labels      = json.dumps([h["month"][:6] for h in hist])
        chart_data        = json.dumps([h["count"] for h in hist])
        resolved_by_month = json.dumps([h.get("resolved", 0) for h in hist])
        chart_max         = max(max(h["count"] for h in hist),
                                max(h.get("resolved",0) for h in hist), 1) + 3
        chart_js = f"""
var CHART_DATA={{
  labels:{chart_labels},
  open:{chart_data},
  resolved:{resolved_by_month},
  yMax:{chart_max}
}};
function initChart(){{
  var canvas=document.getElementById('trendChart');
  if(!canvas)return;
  var W=canvas.offsetWidth||canvas.parentElement&&canvas.parentElement.offsetWidth||0;
  if(W<10){{requestAnimationFrame(initChart);return;}}
  var H=180;
  var dpr=window.devicePixelRatio||1;
  canvas.width=W*dpr; canvas.height=H*dpr;
  canvas.style.width=W+'px'; canvas.style.height=H+'px';
  var ctx=canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  var PAD={{top:28,right:12,bottom:36,left:32}};
  var n=CHART_DATA.labels.length;
  var chartW=W-PAD.left-PAD.right;
  var chartH=H-PAD.top-PAD.bottom;
  var yMax=CHART_DATA.yMax||1;
  var groupW=chartW/n;
  var barW=Math.max(4,groupW*0.32);
  var gap=groupW*0.04;
  var startTime=null;
  var DUR=900;
  function ease(t){{return t<1?1-Math.pow(1-t,4):1;}}
  function draw(ts){{
    try{{
      if(!startTime)startTime=ts;
      var prog=Math.min((ts-startTime)/DUR,1);
      ctx.clearRect(0,0,W,H);
      ctx.strokeStyle='rgba(255,255,255,0.07)';
      ctx.lineWidth=0.5;
      var steps=5;
      for(var i=0;i<=steps;i++){{
        var y=PAD.top+chartH-(i/steps)*chartH;
        ctx.beginPath();ctx.moveTo(PAD.left,y);ctx.lineTo(W-PAD.right,y);ctx.stroke();
        ctx.fillStyle='rgba(255,255,255,0.45)';
        ctx.font='9px system-ui,sans-serif';
        ctx.textAlign='right';
        ctx.fillText(Math.round(yMax*i/steps),PAD.left-4,y+3);
      }}
      for(var gi=0;gi<n;gi++){{
        var cx=PAD.left+gi*groupW+groupW/2;
        var delay0=gi*0.12;
        var p0=ease(Math.max(0,Math.min(1,(prog-delay0)/(1-delay0||0.01))));
        var h0=Math.max(CHART_DATA.open[gi]>0?2:0,(CHART_DATA.open[gi]/yMax)*chartH*p0);
        ctx.fillStyle='rgba(26,111,219,0.88)';
        ctx.fillRect(cx-barW-gap/2,PAD.top+chartH-h0,barW,h0);
        var delay1=gi*0.12+0.05;
        var p1=ease(Math.max(0,Math.min(1,(prog-delay1)/(1-delay1||0.01))));
        var h1=Math.max(CHART_DATA.resolved[gi]>0?2:0,(CHART_DATA.resolved[gi]/yMax)*chartH*p1);
        ctx.fillStyle='rgba(56,161,105,0.88)';
        ctx.fillRect(cx+gap/2,PAD.top+chartH-h1,barW,h1);
        ctx.fillStyle='rgba(255,255,255,0.5)';
        ctx.font='9px system-ui,sans-serif';
        ctx.textAlign='center';
        ctx.fillText(CHART_DATA.labels[gi],cx,H-8);
      }}
      ctx.fillStyle='rgba(26,111,219,0.88)';ctx.fillRect(W-PAD.right-90,6,8,8);
      ctx.fillStyle='rgba(255,255,255,0.6)';ctx.font='9px system-ui,sans-serif';ctx.textAlign='left';ctx.fillText('Open (SR)',W-PAD.right-79,14);
      ctx.fillStyle='rgba(56,161,105,0.88)';ctx.fillRect(W-PAD.right-35,6,8,8);
      ctx.fillStyle='rgba(255,255,255,0.6)';ctx.fillText('Resolved',W-PAD.right-24,14);
      if(prog<1)requestAnimationFrame(draw);
    }}catch(e){{console.error('chart draw error:',e);}}
  }}
  requestAnimationFrame(draw);
}}
// Fire initChart as soon as DOM is ready — works even if DOMContentLoaded already fired
if(document.readyState==='loading'){{
  document.addEventListener('DOMContentLoaded',initChart);
}}else{{
  initChart();
}}"""
        chart_block = (f'<div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.5);'
                       f'text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">'
                       f'SR Ticket Trend — last 6 months</div>'
                       f'<div style="position:relative;height:180px;width:100%">'
                       f'<canvas id="trendChart"></canvas></div>')
    else:
        chart_js    = "function initChart(){}"
        chart_block = '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding-top:1rem">No ticket history available.</div>'

    pulse_colors  = {"frustrated":"#E53E3E","concerned":"#DD6B20","waiting":"#D69E2E","positive":"#38A169","neutral":"#5E6C84"}
    pulse_icons   = {"frustrated":"🔴","concerned":"🟠","waiting":"🟡","positive":"🟢","neutral":"⚪"}
    pulse_items   = data.get("pulse", [])
    pulse_signals = ""
    for p in pulse_items:
        col     = pulse_colors.get(p["sentiment"], "#5E6C84")
        icon    = pulse_icons.get(p["sentiment"], "⚪")
        key     = p.get("key", "")
        snippet = p.get("snippet", "")
        text    = p.get("text", "")
        key_link = (f'<a href="{JIRA_BASE}/browse/{key}" target="_blank" '
                    f'style="font-size:10px;font-weight:700;color:{col};text-decoration:none">{key}</a> · '
                    if key else "")
        pulse_signals += (
            f'<div style="padding:8px 0;border-bottom:.5px solid rgba(255,255,255,0.08);display:flex;gap:9px;align-items:flex-start">'
            f'<span style="font-size:11px;flex-shrink:0;margin-top:1px">{icon}</span>'
            f'<div style="min-width:0">'
            f'<div style="font-size:11px;font-weight:600;color:#fff;margin-bottom:2px">{text}</div>'
            f'<div style="font-size:10px;color:rgba(255,255,255,0.5);line-height:1.45">{key_link}{snippet}</div>'
            f'</div></div>'
        )
    if not pulse_signals:
        pulse_signals = '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding-top:.5rem">No recent customer signals detected.</div>'

    kw_enc  = cust["jql_keyword"].replace(" ", "+").replace('"', '%22')
    ql_jira = f'{JIRA_BASE}/issues/?jql=text+~+%22{kw_enc}%22+AND+statusCategory+%21%3D+Done'

    # ── DATA object and all page JS — goes into companion .js file ────────────
    data_js  = json.dumps({
        "p0p1": len(p0p1), "support": len(support), "features": len(features),
        "eng_tickets": len(eng_tickets), "resolved": len(resolved),
        "pendingEng": pending, "p0keys": p0_keys, "highKeys": high_keys,
        "generated": now, "score": score, "scoreLabel": health_label, "scoreColor": health_color,
    })

    page_js = f"""{chart_js}

var DATA={data_js};
{HEALTH_JS}
window.addEventListener('DOMContentLoaded',function(){{
  try{{runHealth(DATA);}}catch(e){{console.error('runHealth:',e);}}
  try{{buildHealthDrawer(DATA);}}catch(e){{console.error('buildHealthDrawer:',e);}}
}});
function toggleDrawer(dId,mId){{var d=document.getElementById(dId),m=document.getElementById(mId),open=d.classList.contains('open');document.querySelectorAll('.drawer').forEach(function(x){{x.classList.remove('open');}});document.querySelectorAll('.metric').forEach(function(x){{x.classList.remove('active');}});if(!open){{d.classList.add('open');m.classList.add('active');if(dId==='drawer-health'){{try{{buildHealthDrawer(DATA);}}catch(e){{console.error('buildHealthDrawer:',e);}}}};}}}}
function copyJql(btn,key){{var el=document.getElementById('jql-'+key);if(!el)return;navigator.clipboard.writeText(el.textContent.trim()).then(function(){{var orig=btn.textContent;btn.textContent='Copied!';btn.style.color='#38A169';setTimeout(function(){{btn.textContent=orig;btn.style.color='';}},1500);}}).catch(function(){{btn.textContent='Failed';setTimeout(function(){{btn.textContent='Copy';}},1500);}});}}
function buildHealthDrawer(DATA){{
  var factors=[],actions=[];
  if(DATA.p0p1>=3){{factors.push(['-4 pts',DATA.p0p1+' active P0 incidents ('+DATA.p0keys.join(', ')+')', '#E53E3E']);actions.push(['[P0]','Escalate to engineering leadership']);}}
  else if(DATA.p0p1===2){{factors.push(['-3 pts','2 P0 incidents ('+DATA.p0keys.join(', ')+')', '#E53E3E']);actions.push(['[P0]','Both need engineering owner today']);}}
  else if(DATA.p0p1===1){{factors.push(['-2 pts','1 active P0/P1 ('+DATA.p0keys[0]+')', '#DD6B20']);actions.push(['[P0]','Daily updates to customer until resolved']);}}
  else{{factors.push(['+0 pts','No active P0/P1 incidents','#38A169']);}}
  if(DATA.support>=8){{factors.push(['-2 pts','High SR backlog — '+DATA.support+' open','#DD6B20']);actions.push(['[SR]','Close or escalate stale SR tickets']);}}
  else if(DATA.support>=5){{factors.push(['-1 pt','Moderate SR backlog — '+DATA.support+' open','#D69E2E']);actions.push(['[SR]','Target 3 SR resolutions this sprint']);}}
  else{{factors.push(['+0 pts','Healthy SR volume — '+DATA.support+' open','#38A169']);}}
  if(DATA.pendingEng>=4){{factors.push(['-2 pts',DATA.pendingEng+' SR tickets blocked pending eng','#DD6B20']);actions.push(['[ENG]','Set ETAs and communicate to customer']);}}
  else if(DATA.pendingEng>=2){{factors.push(['-1 pt',DATA.pendingEng+' SR tickets pending engineering','#D69E2E']);actions.push(['[ENG]','Chase ETAs this week']);}}
  else{{factors.push(['+0 pts','No SR tickets blocked on engineering','#38A169']);}}
  if(DATA.eng_tickets>=5){{factors.push(['-1 pt',DATA.eng_tickets+' TS engineering tickets open','#D69E2E']);actions.push(['[TS]','Review and triage TS engineering backlog']);}}
  else{{factors.push(['+0 pts',DATA.eng_tickets+' TS engineering tickets','#38A169']);}}
  if(DATA.features>=5){{factors.push(['-1 pt',DATA.features+' TS feature requests open','#D69E2E']);actions.push(['[FR]','Schedule roadmap call']);}}
  else{{factors.push(['+0 pts',DATA.features+' feature requests','#38A169']);}}
  if(DATA.resolved===0){{factors.push(['-1 pt','No SR tickets resolved in 30d','#DD6B20']);actions.push(['[SR]','Close at least one SR ticket']);}}
  else{{factors.push(['+0 pts',DATA.resolved+' SR resolved in 30d','#38A169']);}}
  var fEl=document.getElementById('health-factors');
  if(fEl)fEl.innerHTML=factors.map(function(r){{return '<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:'+r[2]+'1A;color:'+r[2]+';flex-shrink:0;min-width:44px;text-align:center">'+r[0]+'</span><span style="font-size:11px;color:#172B4D;line-height:1.5">'+r[1]+'</span></div>';}}).join('');
  var aEl=document.getElementById('health-actions');
  if(aEl)aEl.innerHTML=actions.length===0?'<p style="font-size:11px;color:#38A169;font-weight:600">No immediate actions needed</p>':actions.map(function(r){{return '<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 5px;border-radius:3px;background:#E6F1FB;color:#0C447C;flex-shrink:0">'+r[0]+'</span><span style="font-size:11px;color:#172B4D;line-height:1.5">'+r[1]+'</span></div>';}}).join('');
}}"""

    mv_col   = "red"    if len(p0p1) > 0     else "green"
    sup_col  = "orange" if len(support) > 5  else "yellow"
    eng_col  = "orange" if len(eng_tickets) > 4 else "blue"
    nav = NAV_CUSTOMER.format(parent=CONFLUENCE_PARENT)

    # ── JQL drawer blocks ──────────────────────────────────────────────────────
    jqls = _jqls
    _JQL_META = [
        ("p0p1",        "🚨", "#E53E3E", "Open P0 / P1"),
        ("support",     "🎫", "#DD6B20", "Support Tickets (SR)"),
        ("features",    "💡", "#1A6FDB", "Feature Requests (TS)"),
        ("eng_tickets", "⚙️",  "#7B2FBE", "Engineering Tickets (TS)"),
        ("resolved",    "✅", "#38A169", "Resolved SR (30d)"),
        ("recent",      "🕐", "#5E6C84", "Recent Activity"),
    ]
    jql_blocks_html = ""
    for jql_key, icon, dot_color, label in _JQL_META:
        q   = jqls.get(jql_key, "")
        enc = q.replace(" ", "+").replace('"', '%22')
        run_url = f"{JIRA_BASE}/issues/?jql={enc}"
        jql_blocks_html += f"""<div class="jql-block">
  <div class="jql-block-head">
    <span class="jql-label"><span class="jql-label-dot" style="background:{dot_color}"></span>{icon} {label}</span>
    <button class="jql-copy" onclick="copyJql(this,'{jql_key}')">Copy</button>
  </div>
  <div class="jql-code" id="jql-{jql_key}">{q}</div>
  <a class="jql-open-link" href="{run_url}" target="_blank">↗ Run in Jira</a>
</div>"""

    portal_link = (f'<div class="ir"><span class="ilabel">Portal</span>'
                   f'<span class="ival"><a class="tlink" href="{cust["portal_url"]}" target="_blank">{cust["portal_url"]}</a></span></div>') if cust.get("portal_url") else ""

    # ── HTML — zero inline scripts, loads companion JS file via src= ──────────
    html = f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">
<title>{cust['name']} — Customer Dashboard</title>
<style>{SHARED_CSS}</style>
</head><body>
{nav}
<div style="background:#0B1F45;padding:1.1rem 1.5rem 1.25rem;display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px;border-bottom:1px solid #122752">
  <div style="display:flex;align-items:flex-start;gap:10px">
    <div style="width:42px;height:42px;background:{cust['logo_bg']};border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800;color:{cust['logo_color']};flex-shrink:0">{cust['initials']}</div>
    <div style="flex:1;min-width:0">
      <div style="font-size:18px;font-weight:700;color:#fff;line-height:1.2">{cust['name']}</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:2px">{cust['cloud']} · {cust['region']} · {engines_str}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;align-items:center">
        <div style="display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.07);border:.5px solid rgba(255,255,255,0.12);border-radius:6px;padding:4px 9px">
          <span style="font-size:9px;font-weight:600;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:.05em">Exec Sponsor</span>
          <span style="font-size:11px;font-weight:700;color:#fff;margin-left:4px">{exec_sponsor}</span>
        </div>
        <div style="display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.07);border:.5px solid rgba(255,255,255,0.12);border-radius:6px;padding:4px 9px">
          <span style="font-size:9px;font-weight:600;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:.05em">TAM / TPM</span>
          <span style="font-size:11px;font-weight:700;color:#fff;margin-left:4px">{tam_primary}</span>
          {f'<span style="font-size:10px;color:rgba(255,255,255,0.35)">· {tam_secondary}</span>' if tam_secondary else ''}
        </div>
        <div style="display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.07);border:.5px solid rgba(255,255,255,0.12);border-radius:6px;padding:4px 9px">
          <span style="font-size:9px;font-weight:600;color:rgba(255,255,255,0.35);text-transform:uppercase;letter-spacing:.05em">Phase</span>
          <span style="font-size:11px;font-weight:700;color:#fff;margin-left:4px">{cust['phase']}</span>
        </div>
      </div>
    </div>
  </div>
  <div style="flex-shrink:0;padding-top:2px">
    <div style="padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;display:flex;align-items:center;gap:5px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15)" id="health-wrap">
      <div style="width:7px;height:7px;border-radius:50%;background:{health_color}" id="health-dot"></div>
      <span id="health-badge" style="color:{health_color}">{health_label}</span>
    </div>
  </div>
</div>
<div style="background:#0D2252;border-bottom:1px solid #122752;padding:.35rem 1.5rem;display:flex;align-items:center;gap:1.5rem">
  {f'<a href="{cust["portal_url"]}" target="_blank" style="font-size:11px;color:#00C2E0;text-decoration:none;font-weight:600">↗ {cust["portal_url"]}</a>' if cust.get("portal_url") else ""}
  <span style="font-size:11px;color:rgba(255,255,255,0.3)">Last refreshed: <span style="color:rgba(255,255,255,0.55);font-weight:500">{now}</span></span>
</div>
<div class="body">
  <div class="metrics" style="grid-template-columns:repeat(8,1fr)">
    <div class="metric" id="m-p0p1" onclick="toggleDrawer('drawer-p0p1','m-p0p1')"><div class="mlabel">Open P0/P1</div><div class="mval {mv_col}">{len(p0p1)}</div><div class="msub">Critical — SR &amp; TS</div></div>
    <div class="metric" id="m-sup"  onclick="toggleDrawer('drawer-sup','m-sup')"><div class="mlabel">Support Tickets</div><div class="mval {sup_col}">{len(support)}</div><div class="msub">SR project · open</div></div>
    <div class="metric" id="m-eng"  onclick="toggleDrawer('drawer-eng','m-eng')"><div class="mlabel">Eng Tickets</div><div class="mval {eng_col}">{len(eng_tickets)}</div><div class="msub">TS project · non-feature</div></div>
    <div class="metric" id="m-feat" onclick="toggleDrawer('drawer-feat','m-feat')"><div class="mlabel">Feature Requests</div><div class="mval blue">{len(features)}</div><div class="msub">TS project · pending</div></div>
    <div class="metric" id="m-res"  onclick="toggleDrawer('drawer-res','m-res')"><div class="mlabel">Resolved (30d)</div><div class="mval green">{len(resolved)}</div><div class="msub">SR · last 30 days</div></div>
    <div class="metric" id="m-health" onclick="toggleDrawer('drawer-health','m-health')"><div class="mlabel">Health Score (WIP)</div><div class="mval" style="color:{health_color}">{score}/10</div><div class="msub">Rule-based</div></div>
    <div class="metric" id="m-jql" onclick="toggleDrawer('drawer-jql','m-jql')" style="border-left:2px solid #E6F1FB"><div class="mlabel">JQL Queries</div><div class="mval" style="font-size:16px;padding-top:3px">🔍</div><div class="msub">Show / hide</div></div>
    <div class="metric" id="m-logic" onclick="toggleDrawer('drawer-logic','m-logic')" style="border-left:2px solid #EEEDFE"><div class="mlabel">Business Logic</div><div class="mval" style="font-size:16px;padding-top:3px">⚙️</div><div class="msub">Show / hide</div></div>
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
  <div class="drawer" id="drawer-p0p1"><div class="drawer-head"><span class="drawer-title">🚨 Open P0 / P1 Incidents ({len(p0p1)}) — SR &amp; TS</span><button class="drawer-close" onclick="toggleDrawer('drawer-p0p1','m-p0p1')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{p0_rows}{p0_trunc}</tbody></table></div>
  <div class="drawer" id="drawer-sup"><div class="drawer-head"><span class="drawer-title">🎫 Support Tickets ({len(support)}) — SR project</span><button class="drawer-close" onclick="toggleDrawer('drawer-sup','m-sup')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{sup_rows}{sup_trunc}</tbody></table></div>
  <div class="drawer" id="drawer-eng"><div class="drawer-head"><span class="drawer-title">⚙️ Engineering Tickets ({len(eng_tickets)}) — TS project · non-feature</span><button class="drawer-close" onclick="toggleDrawer('drawer-eng','m-eng')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{eng_rows}{eng_trunc}</tbody></table></div>
  <div class="drawer" id="drawer-feat"><div class="drawer-head"><span class="drawer-title">💡 Feature Requests ({len(features)}) — TS project</span><button class="drawer-close" onclick="toggleDrawer('drawer-feat','m-feat')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{"".join(ticket_row(i) for i in features) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No feature requests</td></tr>'}{feat_trunc}</tbody></table></div>
  <div class="drawer" id="drawer-res"><div class="drawer-head"><span class="drawer-title">✅ Resolved Last 30 Days ({len(resolved)}) — SR project</span><button class="drawer-close" onclick="toggleDrawer('drawer-res','m-res')">✕</button></div><table><thead><tr><th>Ticket</th><th>Summary</th><th>Priority</th><th>Status</th><th>Age</th></tr></thead><tbody>{"".join(ticket_row(i) for i in resolved) or '<tr><td colspan="5" style="text-align:center;color:#5E6C84;padding:1rem">No resolved tickets</td></tr>'}{res_trunc}</tbody></table></div>
  <div class="drawer" id="drawer-jql">
    <div class="drawer-head">
      <span class="drawer-title">🔍 JQL Queries — <span style="font-weight:400;color:#5E6C84">queries executed for {cust['name']}</span></span>
      <button class="drawer-close" onclick="toggleDrawer('drawer-jql','m-jql')">✕</button>
    </div>
    <div class="jql-grid">{jql_blocks_html}</div>
    <div class="jql-footer">💡 Keyword: <b style="color:#172B4D;margin-left:3px">{cust['jql_keyword']}</b> &nbsp;·&nbsp; SR = customer support · TS = engineering &nbsp;·&nbsp; Click "Run in Jira" to open results live</div>
  </div>
  <div class="drawer" id="drawer-logic">
    <div class="drawer-head">
      <span class="drawer-title">⚙️ Business Logic — <span style="font-weight:400;color:#5E6C84">scoring rules applied to this dashboard</span></span>
      <button class="drawer-close" onclick="toggleDrawer('drawer-logic','m-logic')">✕</button>
    </div>
    <div class="jql-grid" style="grid-template-columns:1fr 1fr 1fr">
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#E53E3E"></span>🚨 P0/P1 Incidents</span></div><div class="jql-code">≥ 3 open → −4 pts&#10;2 open → −3 pts&#10;1 open → −2 pts</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">Source: SR + TS · P0 or P1 label</div></div>
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#DD6B20"></span>🎫 SR Support Backlog</span></div><div class="jql-code">≥ 10 open → −2 pts&#10;≥ 6 open → −1 pt</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">Source: SR project · open tickets</div></div>
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#D69E2E"></span>⏳ Pending Engineering</span></div><div class="jql-code">≥ 4 SR pending → −2 pts&#10;≥ 2 SR pending → −1 pt</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">SR tickets with status "Pending Eng"</div></div>
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#7B2FBE"></span>⚙️ TS Engineering Backlog</span></div><div class="jql-code">≥ 5 open TS eng → −1 pt</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">Source: TS project · non-feature</div></div>
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#1A6FDB"></span>💡 Feature Backlog</span></div><div class="jql-code">≥ 5 open features → −1 pt</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">Source: TS project · Feature / Story</div></div>
      <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#38A169"></span>✅ SR Resolution Cadence</span></div><div class="jql-code">0 resolved in 30d → −1 pt</div><div style="padding:6px 10px 8px;font-size:10px;color:#5E6C84">Source: SR project · resolved ≥ −30d</div></div>
    </div>
    <div class="jql-footer">⚙️ Score starts at 10 · floor 1 &nbsp;·&nbsp; ≥8 Healthy · ≥6 Stable · ≥4 Needs Attention · &lt;4 At Risk</div>
  </div>
  <div class="grid2">
    <div>
      <div class="ai-panel" style="padding:0;overflow:hidden">
        <div style="padding:1rem 1.25rem .85rem;border-bottom:.5px solid rgba(255,255,255,0.08)">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:.75rem">
            <div><div class="ai-eyebrow">✦ Health Analysis</div><div class="ai-title" style="margin-bottom:0">Customer Health Assessment</div></div>
            <div style="text-align:right;flex-shrink:0;margin-left:1rem">
              <div id="health-score-num" style="font-size:32px;font-weight:800;color:{health_color};line-height:1">{score}/10</div>
              <div id="health-score-label" style="font-size:11px;font-weight:700;color:{health_color};margin-top:2px">{health_label}</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="flex:1;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden">
              <div id="health-score-bar" style="height:100%;border-radius:3px;background:{health_color};width:{score*10}%;transition:width .6s ease"></div>
            </div>
            <span style="font-size:10px;color:rgba(255,255,255,0.3);white-space:nowrap">Updated {now}</span>
          </div>
        </div>
        <div style="padding:1rem 1.25rem;border-bottom:.5px solid rgba(255,255,255,0.08)">{chart_block}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0">
          <div style="padding:1rem 1.25rem;border-right:.5px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03)">
            <div style="font-size:11px;font-weight:800;color:#fff;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;padding-bottom:8px;border-bottom:.5px solid rgba(255,255,255,0.1);display:flex;align-items:center;gap:6px"><span style="width:3px;height:14px;background:#00C2E0;border-radius:2px;display:inline-block"></span>Findings</div>
            <div id="ai-findings" style="margin-bottom:1.25rem"><p style="font-size:11px;color:rgba(255,255,255,0.4)">Calculating…</p></div>
            <div style="font-size:11px;font-weight:800;color:#00C2E0;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;padding-bottom:8px;border-bottom:.5px solid rgba(0,194,224,0.2);display:flex;align-items:center;gap:6px"><span style="width:3px;height:14px;background:#00C2E0;border-radius:2px;display:inline-block"></span>Recommended Actions</div>
            <div id="ai-actions"><p style="font-size:11px;color:rgba(255,255,255,0.4)">Calculating…</p></div>
          </div>
          <div style="padding:1rem 1.25rem;background:rgba(0,194,224,0.04)">
            <div style="font-size:11px;font-weight:800;color:#fff;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px;padding-bottom:8px;border-bottom:.5px solid rgba(255,255,255,0.1);display:flex;align-items:center;gap:6px"><span style="width:3px;height:14px;background:#7B2FBE;border-radius:2px;display:inline-block"></span>Customer Signals<span style="font-size:9px;font-weight:500;text-transform:none;letter-spacing:0;color:rgba(255,255,255,0.3);margin-left:2px">· last 21d</span></div>
            {pulse_signals}
          </div>
        </div>
      </div>
    </div>
    <div>
      <div class="sb-sec"><div class="sb-head">📅 Recent Activity</div><div class="tl">{timeline}</div></div>
    </div>
  </div>
</div>
<script src="{js_filename}"></script>
</body></html>"""

    return html, page_js
