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
    eng_bugs    = data.get("eng_bugs",  eng_tickets)   # falls back gracefully if old data
    eng_tasks   = data.get("eng_tasks", eng_tickets)
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
  // In Confluence iframes offsetWidth is often 0 — walk up the DOM for a real width,
  // then fall back to a fixed 600px so bars always render.
  var W=0;
  var el=canvas;
  while(el&&W<10){{W=el.offsetWidth||0;el=el.parentElement;}}
  if(W<10)W=600;
  var H=canvas.parentElement?canvas.parentElement.offsetHeight||220:220;
  if(H<80)H=220;
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
      // Legend — top left, clear of bars
      ctx.fillStyle='rgba(26,111,219,0.88)';ctx.fillRect(PAD.left,5,8,8);
      ctx.fillStyle='rgba(255,255,255,0.55)';ctx.font='9px system-ui,sans-serif';ctx.textAlign='left';ctx.fillText('Open (SR)',PAD.left+11,13);
      ctx.fillStyle='rgba(56,161,105,0.88)';ctx.fillRect(PAD.left+68,5,8,8);
      ctx.fillStyle='rgba(255,255,255,0.55)';ctx.fillText('Resolved',PAD.left+79,13);
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
        chart_block = (f'<div style="position:absolute;inset:0">'
                       f'<canvas id="trendChart" style="width:100%;height:100%"></canvas></div>')
    else:
        chart_js    = "function initChart(){}"
        chart_block = '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding-top:1rem">No ticket history available.</div>'

    # ── Recurring Theme Analysis — keyword matching against Tessell taxonomy ──────
    # Looks at SR tickets created in the last 90 days
    THEME_TAXONOMY = [
        {
            "id": "connectivity",
            "label": "Connectivity",
            "sev": "Critical",
            "shades": ["#F4AFA9", "#E06355", "#B94030"],
            "keywords": ["connect","connection","timeout","unreachable","network","port","firewall","ssh","unable to reach","not accessible","down","unavailable"],
        },
        {
            "id": "performance",
            "label": "Performance",
            "sev": "Critical",
            "shades": ["#F4AFA9", "#E06355", "#B94030"],
            "keywords": ["slow","performance","latency","lag","cpu","memory","iops","throughput","degraded","response time","high load","overload"],
        },
        {
            "id": "monitoring",
            "label": "Monitoring & Alerts",
            "sev": "High",
            "shades": ["#FAD9A8", "#E8A84A", "#B97020"],
            "keywords": ["alert","monitor","metric","alarm","datadog","cloudwatch","not firing","missing","observability","grafana","notification","pager"],
        },
        {
            "id": "backup",
            "label": "Backup & DR",
            "sev": "High",
            "shades": ["#FAD9A8", "#E8A84A", "#B97020"],
            "keywords": ["backup","restore","recovery","snapshot","dr","disaster","rpo","rto","point-in-time","pitr","replication","failover"],
        },
        {
            "id": "auth",
            "label": "Auth & Access",
            "sev": "High",
            "shades": ["#FAD9A8", "#E8A84A", "#B97020"],
            "keywords": ["auth","login","password","credential","permission","access denied","role","privilege","ssl","certificate","iam","token","unauthorized"],
        },
        {
            "id": "patching",
            "label": "Patching & Upgrades",
            "sev": "Medium",
            "shades": ["#AECAF4", "#5E9EE8", "#2060B0"],
            "keywords": ["patch","upgrade","version","update","migration","downtime","maintenance","window","rollback","release"],
        },
        {
            "id": "provisioning",
            "label": "Provisioning",
            "sev": "Medium",
            "shades": ["#AECAF4", "#5E9EE8", "#2060B0"],
            "keywords": ["provision","creat","deploy","spin up","instance","new db","clone","terraform","infra","setup","onboard"],
        },
        {
            "id": "config",
            "label": "Configuration",
            "sev": "Low",
            "shades": ["#d0d0d0", "#a0a0a0", "#686868"],
            "keywords": ["config","parameter","setting","tuning","charset","collation","timezone","init","pg_hba","my.cnf","variable","property"],
        },
    ]

    # Classify each SR ticket from the last 90 days into a theme + month bucket
    from datetime import date as _date
    today_d = _date.today()

    def _month_bucket(iso_str):
        """Return 0=oldest, 1=mid, 2=newest month bucket for a created date."""
        if not iso_str:
            return None
        try:
            d = datetime.fromisoformat(iso_str[:10]).date()
            days_ago = (today_d - d).days
            if days_ago > 90:
                return None
            if days_ago > 60:
                return 0
            elif days_ago > 30:
                return 1
            else:
                return 2
        except Exception:
            return None

    def _classify(summary):
        """Return theme id or None."""
        sl = (summary or "").lower()
        for theme in THEME_TAXONOMY:
            if any(k in sl for k in theme["keywords"]):
                return theme["id"]
        return None

    # Build month labels (oldest → newest)
    month_labels = []
    for offset in [2, 1, 0]:
        mo = today_d.month - offset
        yr = today_d.year + (mo - 1) // 12
        mo = ((mo - 1) % 12) + 1
        month_labels.append(_date(yr, mo, 1).strftime("%b"))

    # Tally theme hits
    theme_counts = {t["id"]: [0, 0, 0] for t in THEME_TAXONOMY}
    theme_examples = {t["id"]: [] for t in THEME_TAXONOMY}

    for issue in support.issues:
        created_str = issue["fields"].get("created", "")
        bucket = _month_bucket(created_str)
        if bucket is None:
            continue
        summary = (issue["fields"].get("summary") or "")
        tid = _classify(summary)
        if tid:
            theme_counts[tid][bucket] += 1
            if len(theme_examples[tid]) < 3:
                key = issue["key"]
                theme_examples[tid].append(f"{key}: {summary[:55]}")

    # Filter to themes with at least 1 ticket, sort by total desc
    active_themes = []
    for theme in THEME_TAXONOMY:
        counts = theme_counts[theme["id"]]
        total  = sum(counts)
        if total > 0:
            active_themes.append({**theme, "monthly": counts, "total": total,
                                   "examples": theme_examples[theme["id"]]})
    active_themes.sort(key=lambda x: x["total"], reverse=True)

    grand_max = max((t["total"] for t in active_themes), default=1)

    # Build JS data array for the animated widget
    import json as _json
    themes_js = _json.dumps([{
        "label":   t["label"],
        "sev":     t["sev"],
        "shades":  t["shades"],
        "monthly": t["monthly"],
        "total":   t["total"],
        "ex":      t["examples"] or [f"No example tickets found"],
    } for t in active_themes])

    months_js   = _json.dumps(month_labels)
    grandmax_js = grand_max

    if active_themes:
        analytics_block = f"""
<div style="padding:.5rem 1.25rem 1rem">
  <!-- Month column headers -->
  <div style="display:grid;grid-template-columns:14px 110px 1fr 24px;gap:8px;margin-bottom:6px;align-items:center">
    <div></div><div></div>
    <div id="ta-mh-{cust['id']}" style="display:flex;gap:2px"></div>
    <div></div>
  </div>

  <div id="ta-rows-{cust['id']}"></div>

  <div style="height:.5px;background:rgba(255,255,255,0.08);margin:.6rem 0"></div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
    <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:6px;border-radius:2px;background:linear-gradient(90deg,#E06355,#B94030)"></div><span style="font-size:10px;color:rgba(255,255,255,0.35)">Critical</span></div>
    <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:6px;border-radius:2px;background:linear-gradient(90deg,#E8A84A,#B97020)"></div><span style="font-size:10px;color:rgba(255,255,255,0.35)">High</span></div>
    <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:6px;border-radius:2px;background:linear-gradient(90deg,#5E9EE8,#2060B0)"></div><span style="font-size:10px;color:rgba(255,255,255,0.35)">Medium</span></div>
    <div style="display:flex;align-items:center;gap:4px"><div style="width:16px;height:6px;border-radius:2px;background:linear-gradient(90deg,#a0a0a0,#686868)"></div><span style="font-size:10px;color:rgba(255,255,255,0.35)">Low</span></div>
    <div style="margin-left:auto;font-size:9px;color:rgba(255,255,255,0.2)">lighter=older · darker=recent</div>
  </div>
</div>
<style>
.ta-row-{cust['id']} {{display:grid;grid-template-columns:14px 110px 1fr 24px;gap:8px;align-items:center;cursor:pointer;margin-bottom:11px}}
.ta-row-{cust['id']}:hover .ta-name {{color:rgba(255,255,255,0.9)!important}}
.ta-seg-track {{display:flex;gap:2px;height:18px}}
.ta-seg {{height:100%;border-radius:4px;flex:0 0 0px;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}}
.ta-seg-lbl {{font-size:9px;font-weight:500;color:rgba(255,255,255,.85);opacity:0;transition:opacity .15s;white-space:nowrap}}
.ta-row-{cust['id']}:hover .ta-seg-lbl {{opacity:1}}
.ta-detail {{max-height:0;overflow:hidden;transition:max-height .38s cubic-bezier(.4,0,.2,1)}}
.ta-detail.open {{max-height:160px}}
.ta-detail-inner {{background:rgba(255,255,255,0.05);border-radius:6px;padding:.6rem .75rem;margin-top:6px;display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.ta-dp-months {{display:flex;gap:6px}}
.ta-dp-month {{flex:1;text-align:center}}
.ta-dp-bar-track {{height:36px;display:flex;align-items:flex-end;justify-content:center}}
.ta-dp-bar {{width:22px;border-radius:2px 2px 0 0;height:0;transition:height .5s cubic-bezier(.22,1,.36,1)}}
.ta-dp-examples {{border-left:.5px solid rgba(255,255,255,0.1);padding-left:8px}}
@keyframes ta-slide-in {{from{{opacity:0;transform:translateX(-5px)}}to{{opacity:1;transform:translateX(0)}}}}
</style>
<script>
(function(){{
  var THEMES={themes_js};
  var MONTHS={months_js};
  var GMAX={grandmax_js};
  var custId='{cust['id']}';
  var openIdx=null;

  // Month headers
  var mhEl=document.getElementById('ta-mh-'+custId);
  if(mhEl){{MONTHS.forEach(function(m){{var d=document.createElement('div');d.style.cssText='flex:1;text-align:center;font-size:9px;color:#A0AEC0;letter-spacing:.04em';d.textContent=m.toUpperCase();mhEl.appendChild(d);}});}}

  var rowsEl=document.getElementById('ta-rows-'+custId);
  if(!rowsEl)return;

  THEMES.forEach(function(t,i){{
    var total=t.total;
    var mMax=Math.max.apply(null,t.monthly)||1;
    var sevColor=t.sev==='Critical'?'#B94030':t.sev==='High'?'#B97020':t.sev==='Medium'?'#2060B0':'#686868';
    var sevBg=t.sev==='Critical'?'#FDECEA':t.sev==='High'?'#FEF3E2':t.sev==='Medium'?'#E8F0FC':'#F4F4F4';

    var wrap=document.createElement('div');
    wrap.style.animation='ta-slide-in .35s ease '+(i*.06)+'s both';

    // Row
    var row=document.createElement('div');
    row.className='ta-row-'+custId;

    var rank=document.createElement('div');
    rank.style.cssText='font-size:10px;color:rgba(255,255,255,0.25);text-align:right';
    rank.textContent=i+1;

    var nameWrap=document.createElement('div');
    nameWrap.innerHTML='<div class="ta-name" style="font-size:11px;font-weight:500;color:rgba(255,255,255,0.55);transition:color .2s">'+t.label+'</div>'
      +'<span style="font-size:8px;font-weight:500;padding:1px 5px;border-radius:10px;color:'+sevColor+';background:'+sevBg+'">'+t.sev+'</span>';

    var track=document.createElement('div');
    track.className='ta-seg-track';
    t.monthly.forEach(function(v,mi){{
      var seg=document.createElement('div');
      seg.className='ta-seg';
      seg.style.background=t.shades[mi];
      seg.dataset.target=v;
      var lbl=document.createElement('div');
      lbl.className='ta-seg-lbl';
      lbl.textContent=v||'';
      seg.appendChild(lbl);
      track.appendChild(seg);
    }});

    var totalEl=document.createElement('div');
    totalEl.style.cssText='font-size:11px;font-weight:500;color:rgba(255,255,255,0.45);text-align:right';
    totalEl.textContent=total;

    row.appendChild(rank);row.appendChild(nameWrap);row.appendChild(track);row.appendChild(totalEl);

    // Detail panel
    var panel=document.createElement('div');
    panel.className='ta-detail';
    var inner=document.createElement('div');
    inner.className='ta-detail-inner';

    var mDiv=document.createElement('div');
    mDiv.className='ta-dp-months';
    t.monthly.forEach(function(v,mi){{
      var diff=mi>0?v-t.monthly[mi-1]:null;
      var dHtml=diff===null?'':diff>0?'<div style="font-size:9px;color:#B94030;margin-top:1px">▲ +'+diff+'</div>':diff<0?'<div style="font-size:9px;color:#2A7A4A;margin-top:1px">▼ '+diff+'</div>':'<div style="font-size:9px;color:#A0AEC0;margin-top:1px">— same</div>';
      var mMonth=document.createElement('div');
      mMonth.className='ta-dp-month';
      mMonth.innerHTML='<div style="font-size:9px;color:rgba(255,255,255,0.35);margin-bottom:2px">'+MONTHS[mi]+'</div>'
        +'<div class="ta-dp-bar-track"><div class="ta-dp-bar" style="background:'+t.shades[mi]+'" data-h="'+Math.round(v/mMax*34)+'"></div></div>'
        +'<div style="font-size:12px;font-weight:500;color:'+t.shades[2]+';margin-top:2px">'+v+'</div>'+dHtml;
      mDiv.appendChild(mMonth);
    }});

    var exDiv=document.createElement('div');
    exDiv.className='ta-dp-examples';
    exDiv.innerHTML='<div style="font-size:9px;color:rgba(255,255,255,0.3);text-transform:uppercase;letter-spacing:.03em;margin-bottom:4px">Recent tickets</div>'
      +t.ex.map(function(e){{
        var colon=e.indexOf(': ');
        var key=colon>0?e.substring(0,colon):'';
        var rest=colon>0?e.substring(colon+2):e;
        if(key&&(key.indexOf('SR-')===0||key.indexOf('TS-')===0)){{
          return '<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-bottom:4px">· <a href="{JIRA_BASE}/browse/'+key+'" target="_blank" style="color:#00C2E0;font-weight:600;text-decoration:none">'+key+'</a> '+rest+'</div>';
        }}
        return '<div style="font-size:10px;color:rgba(255,255,255,0.45);margin-bottom:3px">· '+e+'</div>';
      }}).join('');

    inner.appendChild(mDiv);inner.appendChild(exDiv);panel.appendChild(inner);
    wrap.appendChild(row);wrap.appendChild(panel);
    rowsEl.appendChild(wrap);

    row.addEventListener('click',function(){{
      var isOpen=panel.classList.contains('open');
      document.querySelectorAll('.ta-detail.open').forEach(function(p){{
        p.classList.remove('open');
        p.querySelectorAll('.ta-dp-bar').forEach(function(b){{b.style.height='0';}});
      }});
      if(!isOpen){{
        panel.classList.add('open');
        openIdx=i;
        setTimeout(function(){{
          panel.querySelectorAll('.ta-dp-bar[data-h]').forEach(function(b){{
            b.style.height=b.dataset.h+'px';
          }});
        }},50);
      }} else {{ openIdx=null; }}
    }});
  }});

  // Animate segments in after row entrance
  setTimeout(function(){{
    rowsEl.querySelectorAll('.ta-seg-track').forEach(function(track,ri){{
      var segs=track.querySelectorAll('.ta-seg');
      var delay=ri*70;
      segs.forEach(function(seg,mi){{
        var v=parseInt(seg.dataset.target)||0;
        setTimeout(function(){{
          seg.style.transition='flex-basis .7s cubic-bezier(.22,1,.36,1)';
          seg.style.flexBasis=Math.round(v/GMAX*100)+'%';
        }},delay+mi*55);
      }});
    }});
  }},180);
}})();
</script>"""
    else:
        analytics_block = '<div style="padding:.75rem 1rem;font-size:11px;color:#A0AEC0">No recurring themes detected in the last 90 days.</div>'

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

    # ── Future Engagement data ────────────────────────────────────────────────
    # Detects release labels, fixVersions, due dates on features + eng bugs
    # Also scans SR tickets for maintenance/upgrade/expansion signals

    RELEASE_LABEL_HINTS = [
        "committed","release","patch","target","planned","roadmap",
        "q1-","q2-","q3-","q4-","2026","2025","fix-","hotfix","sprint",
    ]

    def _extract_release_tag(issue_fields):
        """Return best release label/version string, or empty string."""
        fv = issue_fields.get("fixVersions") or []
        if fv:
            return fv[0].get("name", "")
        dd = issue_fields.get("duedate") or ""
        if dd:
            return f"Due {dd}"
        for lbl in (issue_fields.get("labels") or []):
            ll = lbl.lower()
            if any(h in ll for h in RELEASE_LABEL_HINTS):
                return lbl
        return ""

    def _extract_release_date(issue_fields):
        """
        Try to derive an actual date from fixVersions releaseDate, duedate,
        quarter labels (Q1-2026 etc), or version strings. Returns a date object
        or None if nothing can be parsed.
        """
        from datetime import date as _d
        import re as _re

        # fixVersions with a releaseDate field
        fv = issue_fields.get("fixVersions") or []
        for v in fv:
            rd = v.get("releaseDate") or ""
            if rd:
                try: return _d.fromisoformat(rd)
                except Exception: pass

        # explicit duedate
        dd = issue_fields.get("duedate") or ""
        if dd:
            try: return _d.fromisoformat(dd)
            except Exception: pass

        # quarter labels: Q1-2026, Q2-2026 etc → last day of that quarter
        QUARTER_END = {1: (3,31), 2: (6,30), 3: (9,30), 4: (12,31)}
        for lbl in (issue_fields.get("labels") or []):
            m = _re.search(r'[Qq]([1-4])[-_]?(\d{4})', lbl)
            if m:
                q, yr = int(m.group(1)), int(m.group(2))
                mo, dy = QUARTER_END[q]
                try: return _d(yr, mo, dy)
                except Exception: pass

        # fixVersion name that looks like a date: "2026-04-15", "Apr 2026", "April 2026"
        MONTHS_MAP = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                      "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                      "january":1,"february":2,"march":3,"april":4,"june":6,
                      "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
        for v in fv:
            name = v.get("name","")
            # ISO date in name
            m = _re.search(r'(\d{4}-\d{2}-\d{2})', name)
            if m:
                try: return _d.fromisoformat(m.group(1))
                except Exception: pass
            # "Apr 2026" or "April 2026"
            m = _re.search(r'([A-Za-z]+)\s+(\d{4})', name)
            if m:
                mn = MONTHS_MAP.get(m.group(1).lower())
                if mn:
                    try: return _d(int(m.group(2)), mn, 28)  # end of month approx
                    except Exception: pass

        return None

    def _ticket_row_eng(issue, tag_color="#00C2E0"):
        key    = issue["key"]
        f      = issue["fields"]
        summ   = (f.get("summary") or "")[:60]
        tag    = _extract_release_tag(f)
        status = (f.get("status", {}).get("name") or "Open")
        url    = f"{JIRA_BASE}/browse/{key}"
        tag_html = (f'<span style="font-size:9px;background:rgba(0,194,224,0.15);color:{tag_color};'
                    f'padding:1px 6px;border-radius:10px;white-space:nowrap">{tag}</span>') if tag else ""
        return (
            f'<a href="{url}" target="_blank" style="display:flex;align-items:flex-start;gap:8px;'
            f'padding:7px 4px;border-bottom:.5px solid rgba(255,255,255,0.07);text-decoration:none;'
            f'cursor:pointer;transition:background .15s;border-radius:4px"'
            f' onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'"'
            f' onmouseout="this.style.background=\'transparent\'">'
            f'<div style="min-width:0;flex:1">'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">'
            f'<span style="font-size:10px;font-weight:700;color:#00C2E0;flex-shrink:0">{key}</span>'
            f'{tag_html}</div>'
            f'<div style="font-size:11px;color:rgba(255,255,255,0.7);line-height:1.4">{summ}</div>'
            f'</div>'
            f'<span style="font-size:9px;color:rgba(255,255,255,0.3);flex-shrink:0;margin-top:2px">{status}</span>'
            f'</a>'
        )

    # ── Timeline bucketing ────────────────────────────────────────────────────
    from datetime import date as _date2, timedelta as _td
    _today  = _date2.today()
    _7d     = _today + _td(days=7)
    _30d    = _today + _td(days=30)
    _90d    = _today + _td(days=90)

    buckets = {"week": [], "month": [], "quarter": [], "beyond": [], "unscheduled": []}

    for issue in features.issues:
        rd = _extract_release_date(issue["fields"])
        if rd is None:
            tag = _extract_release_tag(issue["fields"])
            if tag:
                buckets["beyond"].append(issue)      # has a label but no parseable date
            else:
                buckets["unscheduled"].append(issue)
        elif rd <= _7d:
            buckets["week"].append(issue)
        elif rd <= _30d:
            buckets["month"].append(issue)
        elif rd <= _90d:
            buckets["quarter"].append(issue)
        else:
            buckets["beyond"].append(issue)

    def _bucket_section(label, issues, color, accent_color="#00C2E0", limit=10):
        if not issues:
            return ""
        html  = (f'<div style="display:flex;align-items:center;gap:8px;margin:10px 0 6px">'
                 f'<div style="width:3px;height:14px;background:{accent_color};border-radius:2px;flex-shrink:0"></div>'
                 f'<span style="font-size:9px;font-weight:700;color:{accent_color};text-transform:uppercase;letter-spacing:.07em">'
                 f'{label}</span>'
                 f'<span style="font-size:9px;color:rgba(255,255,255,0.25)">{len(issues)} ticket{"s" if len(issues)!=1 else ""}</span>'
                 f'</div>')
        for i in issues[:limit]:
            html += _ticket_row_eng(i, accent_color)
        if len(issues) > limit:
            kw_enc = cust["jql_keyword"].replace(" ","+").replace('"','%22')
            more_url = f'{JIRA_BASE}/issues/?jql=project=TS+AND+text+~+"{kw_enc}"+AND+statusCategory!=Done'
            html += (f'<div style="font-size:10px;color:rgba(255,255,255,0.3);padding:6px 4px">'
                     f'<a href="{more_url}" target="_blank" style="color:#00C2E0;text-decoration:none">'
                     f'+{len(issues)-limit} more in Jira →</a></div>')
        return html

    features_html = (
        _bucket_section("Next 7 days",      buckets["week"],        "#E53E3E", "#FC8181")  +
        _bucket_section("Next 30 days",     buckets["month"],       "#FFA94D", "#FFA94D")  +
        _bucket_section("Next 3 months",    buckets["quarter"],     "#00C2E0", "#00C2E0")  +
        _bucket_section("Later / labelled", buckets["beyond"],      "#7B8FA8", "#7B8FA8")  +
        _bucket_section("Unscheduled",      buckets["unscheduled"], "#5E6C84", "#5E6C84", limit=5)
    )
    if not features_html:
        features_html = '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding:.5rem 0">No open feature requests found.</div>'

    # ── Pool ALL ticket types into shared time buckets ───────────────────────
    # Each item: {issue, type: 'feature'|'bug'|'maint'|'expand'}
    all_buckets = {"week": [], "month": [], "quarter": [], "beyond": [], "unscheduled": []}

    def _bucket_key(issue_fields):
        rd = _extract_release_date(issue_fields)
        if rd is None:
            return "beyond" if _extract_release_tag(issue_fields) else "unscheduled"
        if rd <= _7d:   return "week"
        if rd <= _30d:  return "month"
        if rd <= _90d:  return "quarter"
        return "beyond"

    for issue in features.issues:
        all_buckets[_bucket_key(issue["fields"])].append({"issue": issue, "type": "feature"})

    for issue in eng_bugs.issues:
        all_buckets[_bucket_key(issue["fields"])].append({"issue": issue, "type": "bug"})

    for issue in eng_tasks.issues:
        all_buckets[_bucket_key(issue["fields"])].append({"issue": issue, "type": "eng_task"})

    for item in maint_items:
        all_buckets["unscheduled"].append({"item": item, "type": "maint"})

    for item in expand_items:
        all_buckets["unscheduled"].append({"item": item, "type": "expand"})

    TYPE_BADGE = {
        "feature":  ("Feature",    "#00C2E0", "rgba(0,194,224,0.12)"),
        "bug":      ("Bug",        "#FC8181", "rgba(252,129,129,0.12)"),
        "eng_task": ("Eng Support","#FFA94D", "rgba(255,169,77,0.12)"),
        "maint":    ("Planned",    "#A78BFA", "rgba(167,139,250,0.12)"),
        "expand":   ("Expansion",  "#68D391", "rgba(104,211,145,0.12)"),
    }

    def _unified_row(entry):
        typ   = entry["type"]
        badge_label, badge_color, badge_bg = TYPE_BADGE[typ]
        badge = (f'<span style="font-size:8px;font-weight:600;padding:1px 5px;border-radius:8px;'
                 f'color:{badge_color};background:{badge_bg};white-space:nowrap">{badge_label}</span>')
        if "issue" in entry:
            issue  = entry["issue"]
            key    = issue["key"]
            f      = issue["fields"]
            summ   = (f.get("summary") or "")[:65]
            status = (f.get("status", {}).get("name") or "")
            tag    = _extract_release_tag(f)
            url    = f"{JIRA_BASE}/browse/{key}"
            tag_html = (f'<span style="font-size:8px;color:rgba(255,255,255,0.35);'
                        f'background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:8px;'
                        f'white-space:nowrap">{tag}</span>') if tag else ""
            return (
                f'<a href="{url}" target="_blank" style="display:flex;align-items:flex-start;'
                f'gap:8px;padding:7px 4px;border-bottom:.5px solid rgba(255,255,255,0.06);'
                f'text-decoration:none;border-radius:4px;transition:background .15s"'
                f' onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'"'
                f' onmouseout="this.style.background=\'transparent\'">'
                f'<div style="min-width:0;flex:1">'
                f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px;flex-wrap:wrap">'
                f'<span style="font-size:10px;font-weight:700;color:{badge_color};flex-shrink:0">{key}</span>'
                f'{badge}{tag_html}</div>'
                f'<div style="font-size:11px;color:rgba(255,255,255,0.7);line-height:1.4">{summ}</div>'
                f'</div>'
                f'<span style="font-size:9px;color:rgba(255,255,255,0.28);flex-shrink:0;margin-top:2px;white-space:nowrap">{status}</span>'
                f'</a>'
            )
        else:
            item = entry["item"]
            return (
                f'<a href="{item["url"]}" target="_blank" style="display:flex;align-items:flex-start;'
                f'gap:8px;padding:7px 4px;border-bottom:.5px solid rgba(255,255,255,0.06);'
                f'text-decoration:none;border-radius:4px;transition:background .15s"'
                f' onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'"'
                f' onmouseout="this.style.background=\'transparent\'">'
                f'<div style="min-width:0;flex:1">'
                f'<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px">'
                f'<span style="font-size:10px;font-weight:700;color:{badge_color};flex-shrink:0">{item["key"]}</span>'
                f'{badge}</div>'
                f'<div style="font-size:11px;color:rgba(255,255,255,0.7);line-height:1.4">{item["summ"]}</div>'
                f'</div></a>'
            )

    TIMELINE_BUCKETS = [
        ("week",        "Next 7 days",   "#FC8181",              "rgba(252,129,129,0.08)"),
        ("month",       "Next 30 days",  "#FFA94D",              "rgba(255,169,77,0.08)"),
        ("quarter",     "Next 3 months", "#00C2E0",              "rgba(0,194,224,0.06)"),
        ("beyond",      "Later",         "rgba(255,255,255,0.5)","rgba(255,255,255,0.03)"),
        ("unscheduled", "Everything else","rgba(255,255,255,0.3)","rgba(255,255,255,0.02)"),
    ]

    def _timeline_section(bkey, label, accent, bg):
        entries = all_buckets[bkey]
        if not entries:
            return ""
        total = len(entries)
        kw_enc  = cust["jql_keyword"].replace(" ","+").replace('"','%22')
        more_url = f'{JIRA_BASE}/issues/?jql=project%3DTS+AND+text+~+%22{kw_enc}%22+AND+statusCategory%21%3DDone'
        rows = "".join(_unified_row(e) for e in entries[:12])
        more = ""
        if total > 12:
            more = (f'<div style="padding:5px 4px;font-size:10px">'
                    f'<a href="{more_url}" target="_blank" style="color:#00C2E0;text-decoration:none">'
                    f'+{total-12} more in Jira →</a></div>')
        feat_c = sum(1 for e in entries if e["type"]=="feature")
        bug_c  = sum(1 for e in entries if e["type"]=="bug")
        task_c = sum(1 for e in entries if e["type"]=="eng_task")
        oth_c  = sum(1 for e in entries if e["type"] not in ("feature","bug","eng_task"))
        meta   = " · ".join(filter(None,[
            f'{feat_c} feature{"s" if feat_c!=1 else ""}' if feat_c else "",
            f'{bug_c} bug{"s" if bug_c!=1 else ""}' if bug_c else "",
            f'{task_c} eng support' if task_c else "",
            f'{oth_c} other' if oth_c else "",
        ]))
        return (
            f'<div style="background:{bg};border-bottom:.5px solid rgba(255,255,255,0.07)">'
            f'<div style="padding:.65rem 1.25rem .4rem;display:flex;align-items:center;gap:8px">'
            f'<div style="width:3px;height:16px;background:{accent};border-radius:2px;flex-shrink:0"></div>'
            f'<span style="font-size:11px;font-weight:700;color:{accent}">{label}</span>'
            f'<span style="font-size:10px;color:rgba(255,255,255,0.25)">{meta}</span>'
            f'</div>'
            f'<div style="padding:0 1.25rem .65rem">{rows}{more}</div>'
            f'</div>'
        )

    engagement_timeline = "".join(
        _timeline_section(bk, lbl, acc, bg)
        for bk, lbl, acc, bg in TIMELINE_BUCKETS
    ) or '<div style="padding:1.5rem;font-size:11px;color:rgba(255,255,255,0.3)">No upcoming items found for this customer.</div>'

    # Maintenance / upgrade signals from SR tickets
    MAINT_KW = ["upgrade","patch","maintenance","scheduled","planned","migration",
                "window","cutover","go-live","rollout","downtime","activity"]
    EXPAND_KW = ["new environment","additional instance","new region","scale",
                 "expand","additional db","new db","production setup","poc",
                 "evaluation","pilot","onboard","new schema","new database"]

    maint_items   = []
    expand_items  = []
    for issue in list(support.issues) + list(resolved.issues[:50]):
        summ_l = (issue["fields"].get("summary") or "").lower()
        key    = issue["key"]
        summ   = (issue["fields"].get("summary") or "")[:65]
        url    = f"{JIRA_BASE}/browse/{key}"
        if any(k in summ_l for k in MAINT_KW) and key not in [x["key"] for x in maint_items]:
            maint_items.append({"key": key, "summ": summ, "url": url})
        if any(k in summ_l for k in EXPAND_KW) and key not in [x["key"] for x in expand_items]:
            expand_items.append({"key": key, "summ": summ, "url": url})

    def _signal_row(item, color):
        return (
            f'<a href="{item["url"]}" target="_blank" style="display:flex;align-items:flex-start;'
            f'gap:7px;padding:6px 4px;border-bottom:.5px solid rgba(255,255,255,0.07);'
            f'text-decoration:none;border-radius:4px;transition:background .15s"'
            f' onmouseover="this.style.background=\'rgba(255,255,255,0.05)\'"'
            f' onmouseout="this.style.background=\'transparent\'">'
            f'<div style="width:5px;height:5px;border-radius:50%;background:{color};'
            f'flex-shrink:0;margin-top:5px"></div>'
            f'<div style="min-width:0">'
            f'<span style="font-size:10px;font-weight:700;color:{color}">{item["key"]}</span>'
            f'<span style="font-size:11px;color:rgba(255,255,255,0.65);margin-left:6px">{item["summ"]}</span>'
            f'</div></a>'
        )

    maint_html  = "".join(_signal_row(i, "#FFA94D") for i in maint_items[:6]) or \
                  '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding:.5rem 0">No maintenance signals found.</div>'
    expand_html = "".join(_signal_row(i, "#68D391") for i in expand_items[:6]) or \
                  '<div style="font-size:11px;color:rgba(255,255,255,0.3);padding:.5rem 0">No expansion signals found.</div>'

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

  // ── Health bar + score count-up animation ──────────────────────────────────
  var targetScore=DATA.score;
  var targetPct=targetScore*10;

  // Animate the main panel bar
  var bar=document.getElementById('health-score-bar');
  if(bar){{
    setTimeout(function(){{bar.style.width=targetPct+'%';}},120);
  }}

  // Animate the drawer bar (only exists once drawer is opened,
  // but set it preemptively in case drawer is already open)
  var dbar=document.getElementById('health-drawer-bar');
  if(dbar){{
    setTimeout(function(){{dbar.style.width=targetPct+'%';}},120);
  }}

  // Count-up the score number 0 → score over 700ms with easeOutQuart
  var numEl=document.getElementById('health-score-num');
  if(numEl){{
    var start=null;
    var dur=700;
    function countUp(ts){{
      if(!start)start=ts;
      var prog=Math.min((ts-start)/dur,1);
      var ease=1-Math.pow(1-prog,4);
      var cur=Math.round(ease*targetScore);
      numEl.textContent=cur+'/10';
      if(prog<1)requestAnimationFrame(countUp);
      else numEl.textContent=targetScore+'/10';
    }}
    setTimeout(function(){{requestAnimationFrame(countUp);}},80);
  }}
}});
function switchTab(custId,tabId){{
  var tabs=['current','engage'];
  tabs.forEach(function(t){{
    var panel=document.getElementById('tab-'+t+'-'+custId);
    var btn=document.getElementById('tab-btn-'+t+'-'+custId);
    if(!panel||!btn)return;
    var active=(t===tabId);
    panel.style.display=active?'block':'none';
    btn.style.color=active?'#fff':'rgba(255,255,255,0.4)';
    btn.style.background=active?'rgba(255,255,255,0.06)':'transparent';
    btn.style.borderBottom=active?'2px solid #00C2E0':'2px solid transparent';
  }});
}}
function toggleDrawer(dId,mId){{var d=document.getElementById(dId),m=document.getElementById(mId),open=d.classList.contains('open');document.querySelectorAll('.drawer').forEach(function(x){{x.classList.remove('open');}});document.querySelectorAll('.metric').forEach(function(x){{x.classList.remove('active');}});if(!open){{d.classList.add('open');m.classList.add('active');if(dId==='drawer-health'){{try{{buildHealthDrawer(DATA);}}catch(e){{console.error('buildHealthDrawer:',e);}}}};  }}}}
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
      <div style="flex:1;height:8px;background:#F4F5F7;border-radius:4px;overflow:hidden"><div id="health-drawer-bar" style="height:100%;border-radius:4px;background:{health_color};width:0%;transition:width .9s cubic-bezier(.22,1,.36,1)"></div></div>
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

        <!-- ── Panel header: score + bar (always visible) ─────────────────── -->
        <div style="padding:1rem 1.25rem .85rem;border-bottom:.5px solid rgba(255,255,255,0.08)">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:.75rem">
            <div><div class="ai-eyebrow">✦ Health Analysis</div><div class="ai-title" style="margin-bottom:0">Customer Health Assessment</div></div>
            <div style="text-align:right;flex-shrink:0;margin-left:1rem">
              <div id="health-score-num" style="font-size:32px;font-weight:800;color:{health_color};line-height:1">0/10</div>
              <div id="health-score-label" style="font-size:11px;font-weight:700;color:{health_color};margin-top:2px">{health_label}</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="flex:1;height:6px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden">
              <div id="health-score-bar" style="height:100%;border-radius:3px;background:{health_color};width:0%;transition:width .9s cubic-bezier(.22,1,.36,1)"></div>
            </div>
            <span style="font-size:10px;color:rgba(255,255,255,0.3);white-space:nowrap">Updated {now}</span>
          </div>
        </div>

        <!-- ── File-folder tabs ────────────────────────────────────────────── -->
        <div style="display:flex;border-bottom:.5px solid rgba(255,255,255,0.08)">
          <button onclick="switchTab('{cust['id']}','current')"
            id="tab-btn-current-{cust['id']}"
            style="padding:.55rem 1.25rem;font-size:11px;font-weight:600;background:rgba(255,255,255,0.06);
                   color:#fff;border:none;border-right:.5px solid rgba(255,255,255,0.08);
                   border-bottom:2px solid #00C2E0;cursor:pointer;letter-spacing:.02em">
            Current Assessment
          </button>
          <button onclick="switchTab('{cust['id']}','engage')"
            id="tab-btn-engage-{cust['id']}"
            style="padding:.55rem 1.25rem;font-size:11px;font-weight:600;background:transparent;
                   color:rgba(255,255,255,0.4);border:none;border-right:.5px solid rgba(255,255,255,0.08);
                   border-bottom:2px solid transparent;cursor:pointer;letter-spacing:.02em">
            Future Engagement
          </button>
        </div>

        <!-- ════════════════ TAB 1 — CURRENT ASSESSMENT ════════════════════ -->
        <div id="tab-current-{cust['id']}">

          <!-- Chart + Themes row -->
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:.5px solid rgba(255,255,255,0.08)">
            <div style="padding:1rem 1.25rem;border-right:.5px solid rgba(255,255,255,0.08);display:flex;flex-direction:column">
              <div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">SR Ticket Trend — last 6 months</div>
              <div style="flex:1;position:relative;min-height:200px">{chart_block}</div>
            </div>
            <div style="padding:0;overflow:hidden;background:rgba(255,255,255,0.02)">
              <div style="font-size:10px;font-weight:600;color:rgba(255,255,255,0.4);text-transform:uppercase;letter-spacing:.06em;padding:1rem 1.25rem .5rem">Recurring Issue Themes — last 90d</div>
              {analytics_block}
            </div>
          </div>

          <!-- Findings + Signals row -->
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

        <!-- ════════════════ TAB 2 — FUTURE ENGAGEMENT ════════════════════ -->
        <div id="tab-engage-{cust['id']}" style="display:none">

          <!-- Timeline header -->
          <div style="padding:.75rem 1.25rem;border-bottom:.5px solid rgba(255,255,255,0.08);display:flex;align-items:center;gap:1rem">
            <div style="font-size:10px;color:rgba(255,255,255,0.3)">
              All upcoming features, bug fixes and planned activity — organised by target date
            </div>
            <div style="display:flex;gap:8px;margin-left:auto;flex-wrap:wrap">
              <span style="font-size:9px;color:#00C2E0;background:rgba(0,194,224,0.12);padding:2px 7px;border-radius:8px">Feature</span>
              <span style="font-size:9px;color:#FC8181;background:rgba(252,129,129,0.12);padding:2px 7px;border-radius:8px">Bug</span>
              <span style="font-size:9px;color:#FFA94D;background:rgba(255,169,77,0.12);padding:2px 7px;border-radius:8px">Eng Support</span>
              <span style="font-size:9px;color:#A78BFA;background:rgba(167,139,250,0.12);padding:2px 7px;border-radius:8px">Planned</span>
              <span style="font-size:9px;color:#68D391;background:rgba(104,211,145,0.12);padding:2px 7px;border-radius:8px">Expansion</span>
            </div>
          </div>

          <!-- Unified timeline -->
          <div style="overflow-y:auto;max-height:600px">
            {engagement_timeline}
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
