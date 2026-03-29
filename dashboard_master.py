"""
dashboard_master.py — builds the master portfolio HTML dashboard.
"""
import json
from datetime import datetime

from config import CONFLUENCE_PARENT, EST
from templates import SHARED_CSS, NAV_MASTER

# ── Master dashboard builder ───────────────────────────────────────────────────
def build_master_html(customer_results):
    now    = datetime.now(EST).strftime("%b %d, %Y %H:%M EST")
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
        p0col  = "red"    if cr["p0_count"]>0    else "green"
        supcol = "orange" if cr["sup_count"]>5   else "gray" if cr["sup_count"]>2  else "green"
        engcol = "orange" if cr["eng_count"]>4   else "blue"
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
      <div class="cs"><div class="cs-val {supcol}">{cr['sup_count']}</div><div class="cs-label">SR</div></div>
      <div class="cs"><div class="cs-val {engcol}">{cr['eng_count']}</div><div class="cs-label">TS Eng</div></div>
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
            desc  = f"{cr['sup_count']} SR + {cr['eng_count']} TS eng tickets open. Immediate escalation required."
        elif cr["sup_count"]>5:
            sev,sev_cls = "High","sev-high"
            title = f"{c['name']} — {cr['sup_count']} open SR tickets"
            desc  = f"{cr['eng_count']} TS eng tickets · {cr['feat_count']} feature requests pending."
        else:
            sev,sev_cls = "Watch","sev-watch"
            title = f"{c['name']} — monitor closely"
            desc  = f"Phase: {c['phase']}. {cr['sup_count']} SR · {cr['eng_count']} TS eng open."
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

    _HEALTH_ORDER = {"atrisk": 0, "attention": 1, "stable": 2, "healthy": 3}
    heatmap_cells = ""
    for cr in sorted(customer_results, key=lambda x: (_HEALTH_ORDER.get(x["health_key"], 2), -x["p0_count"], -x["sup_count"])):
        c   = cr["config"]
        cls = {"atrisk":"hm-risk","attention":"hm-warn","stable":"hm-stable","healthy":"hm-good"}.get(cr["health_key"],"hm-stable")
        stat= f"{cr['p0_count']} P0s · {cr['sup_count']} SR" if cr["p0_count"]>0 else f"{cr['sup_count']} SR · {cr['eng_count']} TS"
        url = cr.get("dashboard_url","#")
        heatmap_cells += f'<a class="hm-cell {cls}" href="{url}" target="_parent"><div class="hm-name">{c["name"][:18]}</div><div class="hm-stat">{stat}</div></a>'

    # ── TAM load scoring ───────────────────────────────────────────────────────
    # Accumulate raw signals per TAM then normalise to a 0-100 capacity score.
    # Factors (with rationale):
    #   P0/P1 account     +8  — active fire, demands daily TAM attention
    #   At Risk account   +4  — health=atrisk but no P0 yet; high watch load
    #   Needs Attention   +2  — health=attention; moderate monitoring overhead
    #   Open SR tickets   +0.5 each (cap 15) — direct customer-facing workload
    #   Open Eng tickets  +0.3 each (cap 8)  — coordination with engineering
    #   Accounts managed  +3 each (cap 10)   — base management overhead
    #   Impl/Onboarding   +3 per account     — highest-touch lifecycle phase
    # Raw scores are clamped to 0-100 via a soft cap of 80 = "full".
    LOAD_SOFT_CAP = 80   # raw score at which capacity reads 100 %

    tam_map = {}
    for cr in customer_results:
        tam = cr["config"].get("tam_primary","—") or "—"
        if tam == "—": continue
        if tam not in tam_map:
            tam_map[tam] = {"p0":0,"sup":0,"eng":0,"accounts":0,
                            "atrisk":0,"attention":0,"impl":0,
                            "raw_load":0,"customers":[],"crits":[]}
        d = tam_map[tam]
        d["accounts"]  += 1
        d["p0"]        += cr["p0_count"]
        d["sup"]       += cr["sup_count"]
        d["eng"]       += cr["eng_count"]
        d["customers"].append(cr["config"]["name"].split()[0])
        hk = cr["health_key"]
        if hk == "atrisk":    d["atrisk"]    += 1
        if hk == "attention": d["attention"] += 1
        if cr["config"].get("phase") in ("Onboarding","Implementation"): d["impl"] += 1
        if cr["p0_count"] > 0: d["crits"].append(cr["config"]["name"].split()[0])

    for tam, d in tam_map.items():
        raw = (d["p0"]        * 8 +
               d["atrisk"]    * 4 +
               d["attention"] * 2 +
               min(d["sup"] * 0.5, 15) +
               min(d["eng"] * 0.3,  8) +
               min(d["accounts"] * 3, 10) +
               d["impl"]      * 3)
        d["raw_load"] = raw
        d["pct"]      = min(round(raw / LOAD_SOFT_CAP * 100), 100)

    avatar_colors=[{"bg":"#E6F1FB","col":"#0C447C"},{"bg":"#EEEDFE","col":"#3C3489"},
                   {"bg":"#EAF3DE","col":"#27500A"},{"bg":"#FAEEDA","col":"#633806"},
                   {"bg":"#FBEAF0","col":"#72243E"},{"bg":"#E1F5EE","col":"#085041"}]

    # Sort by load descending so most-loaded TAM shows first
    sorted_tams = sorted(tam_map.items(), key=lambda x: -x[1]["pct"])

    # Recommendation: least-loaded TAM who is not over capacity
    best_tam     = next((t for t,d in reversed(sorted_tams) if d["pct"] < 70), None)
    best_tam_row = ""
    if best_tam:
        bd = tam_map[best_tam]
        best_tam_row = (f'<div style="margin:0 1rem .75rem;padding:.6rem .75rem;background:#EAF3DE;'
                        f'border-radius:6px;border:.5px solid #97C459;display:flex;align-items:center;gap:8px">'
                        f'<span style="font-size:13px">✅</span>'
                        f'<div><div style="font-size:11px;font-weight:700;color:#27500A">Recommended for next account: {best_tam}</div>'
                        f'<div style="font-size:10px;color:#3A6E1F;margin-top:1px">'
                        f'{bd["accounts"]} accounts · {bd["pct"]}% capacity · {bd["sup"]} SR open</div></div></div>')

    owner_rows = ""
    for idx, (tam, d) in enumerate(sorted_tams):
        ac      = avatar_colors[idx % len(avatar_colors)]
        parts   = tam.split()
        initials= (parts[0][0]+(parts[1][0] if len(parts)>1 else parts[0][-1])).upper() if parts else "—"
        pct     = d["pct"]
        # Bar colour and status label
        if pct >= 85:
            bar_col, status, status_bg, status_col = "#E53E3E", "Over capacity", "#FFF5F5", "#A32D2D"
        elif pct >= 65:
            bar_col, status, status_bg, status_col = "#DD6B20", "Busy",          "#FFFAF0", "#854F0B"
        elif pct >= 35:
            bar_col, status, status_bg, status_col = "#D69E2E", "Available",     "#FFFDF0", "#7A5A00"
        else:
            bar_col, status, status_bg, status_col = "#38A169", "Has bandwidth", "#EAF3DE", "#27500A"

        custs   = ", ".join(d["customers"][:4]) + ("…" if len(d["customers"]) > 4 else "")
        crit_note = (f' · 🚨 {", ".join(d["crits"][:2])}' if d["crits"] else "")
        impl_note = (f' · 🔄 {d["impl"]} impl' if d["impl"] else "")

        # Breakdown tooltip text
        breakdown = (f'{d["accounts"]} accts'
                     f' · {d["p0"]} P0s'
                     f' · {d["sup"]} SR'
                     f' · {d["eng"]} TS eng'
                     f'{crit_note}{impl_note}')

        owner_rows += f"""<div class="tam-row">
  <div class="tam-top">
    <div class="tam-info">
      <div class="owner-avatar" style="background:{ac['bg']};color:{ac['col']};width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0">{initials}</div>
      <div>
        <div style="font-size:12px;font-weight:700;color:#172B4D;line-height:1.2">{tam}</div>
        <div style="font-size:10px;color:#5E6C84;margin-top:1px">{custs}</div>
      </div>
    </div>
    <span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;background:{status_bg};color:{status_col};flex-shrink:0">{status}</span>
  </div>
  <div class="tam-bar-wrap">
    <div class="tam-bar-track">
      <div class="tam-bar-fill" style="width:{pct}%;background:{bar_col}"></div>
    </div>
    <span class="tam-pct" style="color:{bar_col}">{pct}%</span>
  </div>
  <div class="tam-breakdown">{breakdown}</div>
</div>"""

    top5 = sorted([cr for cr in customer_results if cr["sup_count"]>0 or cr["eng_count"]>0],
                   key=lambda x: -(x["sup_count"]+x["eng_count"]+x["feat_count"]))[:5]
    bar_max = max((cr["sup_count"]+cr["eng_count"]+cr["feat_count"] for cr in top5), default=1)

    trend_rows = ""
    for cr in top5:
        name   = cr["config"]["name"].split()[0][:12]
        url    = cr.get("dashboard_url","#")
        s,e,f  = cr["sup_count"], cr["eng_count"], cr["feat_count"]
        total_w= s+e+f or 1
        sw = round(s/bar_max*100)
        ew = round(e/bar_max*100)
        fw = round(f/bar_max*100)
        trend_rows += (
            f'<a href="{url}" target="_parent" style="display:block;text-decoration:none;'
            f'padding:7px 1rem;border-bottom:.5px solid #F4F5F7;transition:background .12s"'
            f' onmouseover="this.style.background=\'#FAFBFC\'" onmouseout="this.style.background=\'transparent\'">'
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px">'
            f'<span style="font-size:11px;font-weight:600;color:#172B4D">{name}</span>'
            f'<div style="display:flex;gap:8px">'
            f'<span style="font-size:9px;color:#DD6B20;font-weight:600">{s} SR</span>'
            f'<span style="font-size:9px;color:#7B2FBE;font-weight:600">{e} Eng</span>'
            f'<span style="font-size:9px;color:#1A6FDB;font-weight:600">{f} Feat</span>'
            f'</div></div>'
            f'<div style="display:flex;gap:2px;height:6px;border-radius:3px;overflow:hidden;background:#F4F5F7">'
            f'<div class="anim-bar" data-w="{sw}" style="height:100%;background:#DD6B20;width:0%;border-radius:3px 0 0 3px;transition:width .8s cubic-bezier(.22,1,.36,1)"></div>'
            f'<div class="anim-bar" data-w="{ew}" style="height:100%;background:#7B2FBE;width:0%"></div>'
            f'<div class="anim-bar" data-w="{fw}" style="height:100%;background:#1A6FDB;width:0%;border-radius:0 3px 3px 0;transition:width .8s cubic-bezier(.22,1,.36,1) .1s"></div>'
            f'</div></a>'
        )

    # Pipeline with per-phase customer names for expand dropdown
    phase_customers = {"Onboarding":[],"Implementation":[],"Stabilisation":[],"Production":[],"Steady State":[]}
    for cr in customer_results:
        p = cr["config"].get("phase","")
        if p in phase_customers:
            phase_customers[p].append({"name": cr["config"]["name"], "url": cr.get("dashboard_url","#"),
                                        "sup": cr["sup_count"], "p0": cr["p0_count"]})

    pipeline_html = ""
    phase_defs = [
        ("Onboarding",    phase_counts["Onboarding"],    "#378ADD","#E6F1FB"),
        ("Implementation",phase_counts["Implementation"],"#BA7517","#FAEEDA"),
        ("Stabilisation", phase_counts["Stabilisation"], "#E24B4A","#FCEBEB"),
        ("Production",    phase_counts["Production"],    "#1D9E75","#E1F5EE"),
        ("Steady State",  phase_counts["Steady State"],  "#5F5E5A","#F1EFE8"),
    ]
    for label, count, color, bg in phase_defs:
        pct  = round(count/pipe_max*100)
        pid  = "pipe-" + label.replace(" ","-").lower()
        bar_label = "" if pct<=15 else str(count)
        cust_label = "customer" if count==1 else "customers"
        no_cust = f'<span style="font-size:10px;color:{color}99">No customers</span>'
        pills = []
        for c in phase_customers[label]:
            suffix = "  🚨" if c["p0"]>0 else (f'  {c["sup"]}SR' if c["sup"]>0 else "")
            pills.append(
                f'<a href="{c["url"]}" target="_parent" style="display:inline-flex;align-items:center;gap:4px;'
                f'padding:3px 8px;border-radius:12px;border:.5px solid {color}44;background:{bg};'
                f'font-size:10px;font-weight:600;color:{color};text-decoration:none;margin:2px">'
                f'{c["name"].split()[0][:12]}{suffix}</a>'
            )
        cust_pills = "".join(pills) or no_cust
        pipeline_html += (
            f'<div class="phase-row" style="cursor:pointer" onclick="togglePipe(\'{pid}\')">'
            f'<span class="phase-label">{label}</span>'
            f'<div class="phase-track">'
            f'<div class="anim-bar phase-fill" data-w="{max(pct,8)}" style="width:0%;background:{color};color:{bg}">'
            f'{bar_label}</div></div>'
            f'<span class="phase-count" style="color:{color}">{count}</span>'
            f'</div>'
            f'<div id="{pid}" style="display:none;padding:6px 1.1rem 8px;background:{bg};'
            f'border-radius:6px;margin:-4px 0 6px 110px">'
            f'<div style="font-size:9px;font-weight:600;color:{color};text-transform:uppercase;'
            f'letter-spacing:.05em;margin-bottom:4px">{label} · {count} {cust_label}</div>'
            f'{cust_pills}'
            f'</div>'
        )

    highlights = []
    crit = [cr for cr in customer_results if cr["p0_count"]>0]
    if crit:
        highlights.append(("🚨", "P0/P1 Incidents",
            f'<b>{sum(c["p0_count"] for c in crit)} active</b> — {", ".join(c["config"]["name"].split()[0] for c in crit[:3])} need immediate attention',
            "#A32D2D", "#FFF5F5", "#F09595"))
    new_impl = [cr for cr in customer_results if cr["config"].get("phase") in ("Onboarding","Implementation")]
    if new_impl:
        highlights.append(("🔄", "In Implementation",
            f'<b>{len(new_impl)} customers</b> active — {", ".join(c["config"]["name"].split()[0] for c in new_impl[:3])}',
            "#854F0B", "#FFFAF0", "#EF9F27"))
    total_sr  = sum(c["sup_count"]  for c in real)
    total_eng = sum(c["eng_count"]  for c in real)
    total_feat= sum(c["feat_count"] for c in real)
    highlights.append(("📊", "Portfolio Snapshot",
        f'<b>{total_sr} SR open</b> · <b>{total_eng} TS eng</b> · <b>{total_feat} features</b> across {total} customers',
        "#0C447C", "#E6F1FB", "#85B7EB"))
    prod = [cr for cr in customer_results if cr["config"].get("phase")=="Production"]
    if prod:
        highlights.append(("✅", "In Production",
            f'<b>{len(prod)} customers</b> live — {", ".join(c["config"]["name"].split()[0] for c in prod[:3])}',
            "#27500A", "#EAF3DE", "#97C459"))

    # Build tab strip for highlights
    hl_tabs = ""
    hl_panels = ""
    for idx,(icon, title, body, tcol, tbg, tborder) in enumerate(highlights[:4]):
        active_tab   = "border-bottom:2px solid #172B4D;color:#172B4D;background:#fff;" if idx==0 else "border-bottom:2px solid transparent;color:#5E6C84;background:transparent;"
        active_panel = "" if idx==0 else 'style="display:none"'
        hl_tabs   += (f'<button onclick="switchHL({idx})" id="hl-tab-{idx}" '
                      f'style="padding:.5rem .9rem;font-size:11px;font-weight:600;border:none;'
                      f'border-top:2px solid transparent;cursor:pointer;{active_tab}">'
                      f'{icon} {title}</button>')
        hl_panels += (f'<div id="hl-panel-{idx}" {active_panel} '
                      f'style="padding:.75rem 1rem;background:{tbg};border-top:.5px solid {tborder}33">'
                      f'<div style="font-size:11px;color:{tcol};line-height:1.6">{body}</div>'
                      f'</div>')

    # TAM capacity — horizontal card row instead of long vertical panel
    tam_cards = ""
    for idx, (tam, d) in enumerate(sorted_tams):
        ac   = avatar_colors[idx % len(avatar_colors)]
        pct  = d["pct"]
        parts = tam.split()
        initials = (parts[0][0]+(parts[1][0] if len(parts)>1 else parts[0][-1])).upper() if parts else "—"
        if pct >= 85:   bar_col,status,scol = "#E53E3E","Over capacity","#A32D2D"
        elif pct >= 65: bar_col,status,scol = "#DD6B20","Busy",         "#854F0B"
        elif pct >= 35: bar_col,status,scol = "#D69E2E","Available",    "#7A5A00"
        else:           bar_col,status,scol = "#38A169","Has bandwidth","#27500A"
        custs = ", ".join(d["customers"][:3]) + ("…" if len(d["customers"])>3 else "")
        tam_cards += (
            f'<div style="background:#fff;border:.5px solid #DFE1E6;border-radius:10px;padding:.85rem 1rem;min-width:0">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
            f'<div style="width:30px;height:30px;border-radius:50%;background:{ac["bg"]};color:{ac["col"]};'
            f'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">{initials}</div>'
            f'<div style="min-width:0;flex:1">'
            f'<div style="font-size:12px;font-weight:700;color:#172B4D;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{tam.split()[0]}</div>'
            f'<div style="font-size:9px;color:#5E6C84;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{custs}</div>'
            f'</div>'
            f'<span style="font-size:9px;font-weight:700;color:{scol};flex-shrink:0">{pct}%</span>'
            f'</div>'
            f'<div style="height:6px;background:#F4F5F7;border-radius:3px;overflow:hidden;margin-bottom:5px">'
            f'<div class="anim-bar" data-w="{pct}" style="height:100%;border-radius:3px;background:{bar_col};width:0%;transition:width .9s cubic-bezier(.22,1,.36,1) {idx*0.08:.2f}s"></div>'
            f'</div>'
            f'<div style="font-size:9px;color:#A0AEC0">{d["accounts"]} accts · {d["sup"]} SR · {d["eng"]} TS eng</div>'
            f'</div>'
        )



    # ── P0/P1 incidents tab content — pre-computed to avoid nested f-string ──
    no_p0_html = ('<div style="padding:3rem;text-align:center;background:#fff;border-radius:10px;'
                  'border:.5px solid #DFE1E6"><div style="font-size:2rem;margin-bottom:.5rem">✅</div>'
                  '<div style="font-size:14px;font-weight:700;color:#27500A">No active P0/P1 incidents</div>'
                  '<div style="font-size:12px;color:#5E6C84;margin-top:4px">All customers operating normally</div></div>')
    p0_customers_cards = ""
    for cr in [x for x in customer_results if x["p0_count"] > 0]:
        c = cr["config"]
        p0_customers_cards += (
            f'<a class="cust-card" href="{cr.get("dashboard_url","#")}" target="_parent" '
            f'style="text-decoration:none;color:inherit">'
            f'<div class="card-header">'
            f'<div class="card-logo" style="background:{c["logo_bg"]};color:{c["logo_color"]}">{c["initials"]}</div>'
            f'<div><div class="card-name">{c["name"]}</div><div class="card-meta">{c["region"]}</div></div>'
            f'<div class="health-pill" style="background:#FFF5F5;border:1px solid #F09595;color:#A32D2D">'
            f'<div class="hp-dot" style="background:#E53E3E"></div>{cr["p0_count"]} P0/P1</div>'
            f'</div>'
            f'<div class="card-body"><div class="card-stats">'
            f'<div class="cs"><div class="cs-val red">{cr["p0_count"]}</div><div class="cs-label">P0/P1</div></div>'
            f'<div class="cs"><div class="cs-val orange">{cr["sup_count"]}</div><div class="cs-label">SR</div></div>'
            f'<div class="cs"><div class="cs-val blue">{cr["eng_count"]}</div><div class="cs-label">TS Eng</div></div>'
            f'<div class="cs"><div class="cs-val blue">{cr["feat_count"]}</div><div class="cs-label">Features</div></div>'
            f'</div>'
            f'<div class="card-footer"><span class="phase-lbl">{c["phase"]}</span>'
            f'<span class="drill-btn">View Dashboard →</span></div></div></a>'
        )
    p0_tab_top = (
        f'<div class="action-strip"><div class="action-head">'
        f'<div class="action-head-title"><span style="font-size:14px">🔴</span> Active P0/P1 Incidents '
        f'<span class="action-head-badge">{total_p0} open</span></div></div>'
        f'<div class="action-items">{"".join(action_items)}</div></div>'
    ) if total_p0 > 0 else no_p0_html
    p0_cards_section = (
        f'<div style="margin-top:1rem"><div class="sec">'
        f'<div class="sec-head"><span class="sec-title">Customers with active P0/P1</span></div>'
        f'<div class="cards-grid" style="padding:.75rem 1rem">{p0_customers_cards}</div>'
        f'</div></div>'
    ) if total_p0 > 0 else ""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">
<title>CSE - Customer Portfolio</title>
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
.card-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:.7rem}}
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
.tam-row{{padding:.75rem 1rem;border-bottom:.5px solid #DFE1E6}}
.tam-row:last-child{{border-bottom:none}}
.tam-top{{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px}}
.tam-info{{display:flex;align-items:center;gap:8px;min-width:0}}
.tam-bar-wrap{{display:flex;align-items:center;gap:7px;margin-bottom:4px}}
.tam-bar-track{{flex:1;height:7px;background:#F4F5F7;border-radius:4px;overflow:hidden}}
.tam-bar-fill{{height:100%;border-radius:4px;transition:width .8s ease}}
.tam-pct{{font-size:11px;font-weight:700;width:32px;text-align:right;flex-shrink:0}}
.tam-breakdown{{font-size:10px;color:#A0AEC0;line-height:1.4}}
.master-logic-drawer{{display:none;border-top:.5px solid #DFE1E6;background:#FAFBFC}}
.master-logic-drawer.open{{display:block}}
.phase-expand{{border-radius:6px;overflow:hidden;margin:-4px 0 6px 110px}}
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
      <div style="font-size:12px;font-weight:500;color:rgba(255,255,255,0.55)">{datetime.now(EST).strftime("%B %d, %Y")}</div>
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

  <!-- ── Page-level tab bar ───────────────────────────────────────────────── -->
  <div style="display:flex;gap:0;border-bottom:2px solid #DFE1E6;margin-bottom:1.25rem">
    <button id="ptab-btn-0" onclick="switchPageTab(0)"
      style="padding:.6rem 1.4rem;font-size:12px;font-weight:700;border:none;background:transparent;
             color:#172B4D;border-bottom:3px solid #0B1F45;margin-bottom:-2px;cursor:pointer;letter-spacing:.01em">
      Portfolio Overview
    </button>
    <button id="ptab-btn-1" onclick="switchPageTab(1)"
      style="padding:.6rem 1.4rem;font-size:12px;font-weight:700;border:none;background:transparent;
             color:#5E6C84;border-bottom:3px solid transparent;margin-bottom:-2px;cursor:pointer;letter-spacing:.01em">
      All Customers
    </button>
    <button id="ptab-btn-2" onclick="switchPageTab(2)"
      style="padding:.6rem 1.4rem;font-size:12px;font-weight:700;border:none;background:transparent;
             color:#5E6C84;border-bottom:3px solid transparent;margin-bottom:-2px;cursor:pointer;letter-spacing:.01em">
      🔴 P0/P1 Incidents
      {f'<span style="margin-left:5px;font-size:9px;padding:1px 6px;border-radius:8px;background:#FFF5F5;color:#A32D2D;border:.5px solid #F09595">{total_p0}</span>' if total_p0>0 else ''}
    </button>
  </div>

  <!-- ══════════════ TAB 0 — PORTFOLIO OVERVIEW ══════════════ -->
  <div id="ptab-panel-0">

    <!-- Action required strip -->
    <div class="action-strip" style="margin-bottom:1.1rem">
      <div class="action-head">
        <div class="action-head-title"><span style="font-size:14px">🔴</span> Action Required
          <span class="action-head-badge">{min(3,len([cr for cr in customer_results if cr['p0_count']>0 or cr['sup_count']>5]))} items</span>
        </div>
      </div>
      <div class="action-items">{''.join(action_items)}</div>
    </div>

    <!-- Highlights tab strip -->
    <div style="background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.1rem">
      <div style="display:flex;border-bottom:.5px solid #DFE1E6;overflow-x:auto">
        {hl_tabs}
      </div>
      {hl_panels}
    </div>

    <!-- TAM / TPM capacity — horizontal card row -->
    <div style="background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.1rem">
      <div style="padding:.6rem 1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:12px;font-weight:700;color:#172B4D">TAM / TPM Capacity</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-size:10px;color:#5E6C84">sorted by load</span>
          <button onclick="toggleMasterLogic()" id="master-logic-btn"
            style="font-size:10px;font-weight:600;color:#7B2FBE;background:#EEEDFE;border:.5px solid #C4B9F5;
                   border-radius:10px;padding:2px 9px;cursor:pointer;line-height:1.6">⚙️ Logic</button>
        </div>
      </div>
      <div class="master-logic-drawer" id="master-logic-drawer">
        <div style="padding:.75rem 1rem .25rem;font-size:10px;font-weight:700;color:#5E6C84;text-transform:uppercase;letter-spacing:.06em">TAM Load Scoring Formula</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem;padding:.5rem 1rem 1rem">
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#E53E3E"></span>🚨 P0/P1 Account</span></div><div class="jql-code">+8 pts · active fire, daily calls</div></div>
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#FC8181"></span>⚠️ At Risk</span></div><div class="jql-code">+4 pts · high watch load</div></div>
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#FFC107"></span>👀 Needs Attention</span></div><div class="jql-code">+2 pts · regular check-ins</div></div>
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#DD6B20"></span>🎫 SR Tickets</span></div><div class="jql-code">+0.5 each · cap 15 pts</div></div>
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#7B2FBE"></span>⚙️ TS Eng Tickets</span></div><div class="jql-code">+0.3 each · cap 8 pts</div></div>
          <div class="jql-block"><div class="jql-block-head"><span class="jql-label"><span class="jql-label-dot" style="background:#0D6E85"></span>🔄 Impl/Onboarding</span></div><div class="jql-code">+3 pts per active impl</div></div>
        </div>
        <div class="jql-footer">≥85% Over capacity 🔴 · 65–84% Busy 🟠 · 35–64% Available 🟡 · &lt;35% Has bandwidth 🟢</div>
      </div>
      {best_tam_row}
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;padding:.75rem 1rem 1rem">
        {tam_cards}
      </div>
    </div>

    <!-- Main 2-col grid: pipeline + ticket load | heatmap -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.1rem;align-items:start">
      <div>
        <div class="sec" style="margin-bottom:1.1rem">
          <div class="sec-head">
            <span class="sec-title">Implementation pipeline</span>
            <span style="font-size:10px;color:#5E6C84">{total} total · click phase to expand</span>
          </div>
          <div class="pipeline">{pipeline_html}</div>
        </div>
        <div class="sec">
          <div class="sec-head">
            <span class="sec-title">Open ticket load by customer</span>
            <div style="display:flex;gap:10px">
              <span style="font-size:9px;color:#DD6B20;font-weight:600">■ SR</span>
              <span style="font-size:9px;color:#7B2FBE;font-weight:600">■ Eng</span>
              <span style="font-size:9px;color:#1A6FDB;font-weight:600">■ Features</span>
            </div>
          </div>
          <div style="padding:4px 0">{trend_rows}</div>
        </div>
      </div>
      <div class="sec">
        <div class="sec-head">
          <span class="sec-title">Customer health heatmap</span>
          <span style="font-size:10px;color:#5E6C84">Click any cell to drill in</span>
        </div>
        <div class="heatmap">{heatmap_cells}</div>
      </div>
    </div>

  </div>

  <!-- ══════════════ TAB 1 — ALL CUSTOMERS ══════════════ -->
  <div id="ptab-panel-1" style="display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:.85rem;flex-wrap:wrap;gap:8px">
      <div style="font-size:13px;font-weight:700;color:#172B4D">{total} customers</div>
      <div class="filter-bar">
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

  <!-- ══════════════ TAB 2 — P0/P1 INCIDENTS ══════════════ -->
  <div id="ptab-panel-2" style="display:none">
    {p0_tab_top}
    {p0_cards_section}
  </div>

</div>
<script>
function filterCards(h,btn){{document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.cust-card').forEach(el=>{{el.style.display=h==='all'||el.dataset.health===h?'':'none';}});}}
function searchCards(q){{q=q.toLowerCase();document.querySelectorAll('.cust-card').forEach(el=>{{el.style.display=(el.dataset.name||'').includes(q)?'':'none';}});}}
function toggleMasterLogic(){{const d=document.getElementById('master-logic-drawer'),btn=document.getElementById('master-logic-btn'),open=d.classList.contains('open');d.classList.toggle('open');btn.textContent=open?'⚙️ Logic':'⚙️ Hide';btn.style.background=open?'#EEEDFE':'#7B2FBE';btn.style.color=open?'#7B2FBE':'#fff';btn.style.borderColor=open?'#C4B9F5':'#7B2FBE';}}
function togglePipe(id){{const el=document.getElementById(id);if(el)el.style.display=el.style.display==='none'?'block':'none';}}
function switchHL(idx){{for(var i=0;i<4;i++){{var t=document.getElementById('hl-tab-'+i),p=document.getElementById('hl-panel-'+i);if(!t||!p)continue;var on=i===idx;t.style.borderBottom=on?'2px solid #172B4D':'2px solid transparent';t.style.color=on?'#172B4D':'#5E6C84';t.style.background=on?'#fff':'transparent';p.style.display=on?'block':'none';}}}}
function switchPageTab(idx){{
  for(var i=0;i<3;i++){{
    var btn=document.getElementById('ptab-btn-'+i);
    var panel=document.getElementById('ptab-panel-'+i);
    if(!btn||!panel)continue;
    var on=i===idx;
    panel.style.display=on?'block':'none';
    btn.style.color=on?'#172B4D':'#5E6C84';
    btn.style.borderBottom=on?'3px solid #0B1F45':'3px solid transparent';
    btn.style.fontWeight=on?'700':'600';
  }}
  if(idx===0){{
    setTimeout(function(){{
      document.querySelectorAll('.anim-bar[data-w]').forEach(function(el,i){{
        setTimeout(function(){{el.style.width=el.dataset.w+'%';}},i*20);
      }});
    }},50);
  }}
}}
window.addEventListener('DOMContentLoaded',function(){{
  setTimeout(function(){{
    document.querySelectorAll('.anim-bar[data-w]').forEach(function(el,i){{
      setTimeout(function(){{el.style.width=el.dataset.w+'%';}},i*20);
    }});
  }},150);
}});
</script></body></html>"""
