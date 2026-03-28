"""
templates.py — shared CSS, nav HTML, and the client-side health score JS.
These are static strings injected into every generated HTML page.
"""

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
.metric{background:#fff;border-radius:8px;padding:.9rem 1rem;border:.5px solid #DFE1E6;cursor:pointer;transition:box-shadow .15s}
.metric:hover{box-shadow:0 0 0 2px #1A6FDB}
.metric.active{box-shadow:0 0 0 2px #1A6FDB;background:#F0F7FF}
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
.sb-sec{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1rem}
.sb-head{padding:.7rem 1rem;border-bottom:.5px solid #DFE1E6;font-size:12px;font-weight:700;color:#172B4D}
.ir{display:flex;align-items:center;justify-content:space-between;padding:7px 1rem;border-bottom:.5px solid #DFE1E6}
.ir:last-child{border-bottom:none}
.ilabel{font-size:11px;color:#5E6C84}.ival{font-size:11px;font-weight:600;color:#172B4D}
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
.drawer{background:#fff;border-radius:10px;border:.5px solid #DFE1E6;overflow:hidden;margin-bottom:1.25rem;display:none}
.drawer.open{display:block}
.drawer-head{padding:.7rem 1.1rem;border-bottom:.5px solid #DFE1E6;display:flex;align-items:center;justify-content:space-between}
.drawer-title{font-size:12px;font-weight:700;color:#172B4D}
.drawer-close{font-size:14px;color:#5E6C84;cursor:pointer;background:none;border:none;padding:0 4px;line-height:1}
.jql-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;padding:1rem 1.25rem}
.jql-block{background:#F8F9FA;border:.5px solid #DFE1E6;border-radius:8px;overflow:hidden}
.jql-block-head{display:flex;align-items:center;justify-content:space-between;padding:7px 10px;background:#F4F5F7;border-bottom:.5px solid #DFE1E6}
.jql-label{font-size:10px;font-weight:700;color:#5E6C84;text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:center;gap:5px}
.jql-label-dot{width:6px;height:6px;border-radius:50%}
.jql-copy{font-size:10px;font-weight:600;color:#1A6FDB;background:none;border:none;cursor:pointer;padding:0;line-height:1}
.jql-copy:hover{text-decoration:underline}
.jql-code{font-family:'SF Mono',ui-monospace,Menlo,Monaco,monospace;font-size:10.5px;color:#172B4D;line-height:1.65;padding:10px;word-break:break-word;white-space:pre-wrap}
.jql-open-link{display:inline-block;margin:0 10px 10px;font-size:10px;font-weight:600;color:#1A6FDB;text-decoration:none}
.jql-open-link:hover{text-decoration:underline}
.jql-footer{padding:.6rem 1.25rem;background:#FAFBFC;border-top:.5px solid #DFE1E6;font-size:10px;color:#5E6C84;display:flex;align-items:center;gap:5px}
"""

NAV_MASTER = """<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span><span class="nl active">Customers</span>
    <span class="nl">Incidents</span><span class="nl">Onboarding</span>
  </div>
</div>"""

NAV_CUSTOMER = """<div class="nav">
  <div class="nav-links">
    <a class="nl" href="https://tessell.atlassian.net/wiki/spaces/CSE/overview" target="_parent">Home</a>
    <span class="nl">Runbooks</span><span class="nl active">Customers</span>
    <span class="nl">Incidents</span><span class="nl">Onboarding</span>
  </div>
  <a class="nav-back" href="https://tessell.atlassian.net/wiki/spaces/CSE/pages/{parent}" target="_parent">← All Customers</a>
</div>"""

HEALTH_JS = """
function runHealth(DATA) {
  const elF=document.getElementById('ai-findings'),elA=document.getElementById('ai-actions'),sc=document.getElementById('ai-score');
  let score=10,findings=[],actions=[];
  if(DATA.p0p1>=3){score-=4;findings.push(`<b style="color:#FC8181">${DATA.p0p1} active P0 incidents</b> (${DATA.p0keys.join(', ')})`);actions.push(`Escalate ${DATA.p0keys[0]} to engineering leadership for same-day resolution`);}
  else if(DATA.p0p1===2){score-=3;findings.push(`<b style="color:#FC8181">2 active P0 incidents</b> (${DATA.p0keys.join(', ')})`);actions.push(`Both need an engineering owner today`);}
  else if(DATA.p0p1===1){score-=2;findings.push(`<b style="color:#FFC107">1 active P0/P1</b> (${DATA.p0keys[0]})`);actions.push(`Ensure ${DATA.p0keys[0]} has daily updates to customer`);}
  else{findings.push('<b style="color:#68D391">No active P0/P1 incidents</b>');}
  if(DATA.support>=8){score-=2;findings.push(`High SR backlog: <b>${DATA.support} support tickets</b> open`);}
  else if(DATA.support>=5){score-=1;findings.push(`Moderate SR backlog: <b>${DATA.support} support tickets</b>`);}
  else{findings.push(`<b style="color:#68D391">Healthy SR volume</b>: ${DATA.support} open`);}
  if(DATA.pendingEng>=4){score-=2;findings.push(`<b>${DATA.pendingEng} SR tickets stuck pending engineering</b>`);actions.push(`Set ETAs on all ${DATA.pendingEng} blocked SR tickets`);}
  else if(DATA.pendingEng>=2){score-=1;findings.push(`${DATA.pendingEng} SR tickets pending engineering`);}
  if(DATA.eng_tickets>=5){score-=1;findings.push(`Engineering backlog: <b>${DATA.eng_tickets} TS tickets</b>`);actions.push('Review and prioritise TS engineering backlog');}
  else{findings.push(`<b style="color:#68D391">TS engineering queue</b>: ${DATA.eng_tickets} open`);}
  if(DATA.features>=5){score-=1;findings.push(`Large feature backlog: <b>${DATA.features} requests</b>`);actions.push('Schedule a feature roadmap call');}
  if(DATA.resolved===0){score-=1;findings.push('<b style="color:#FFC107">No SR tickets resolved in 30 days</b>');}
  else{findings.push(`<b style="color:#68D391">${DATA.resolved} SR resolved</b> in last 30 days`);}
  score=Math.max(1,Math.min(10,score));
  const color=score>=8?'#68D391':score>=6?'#FFC107':'#FC8181';
  const label=score>=8?'Healthy':score>=6?'Stable':score>=4?'Needs Attention':'At Risk';
  const badge=document.getElementById('health-badge'),dot=document.getElementById('health-dot');
  if(badge){badge.textContent=label;badge.style.color=color;}
  if(dot){dot.style.background=color;}
  if(badge&&badge.parentElement){badge.parentElement.style.borderColor=color+'4D';badge.parentElement.style.background=color+'1A';}
  const bar=document.getElementById('health-score-bar'),barWrap=document.getElementById('health-score-label');
  if(bar){bar.style.width=(score*10)+'%';bar.style.background=color;}
  if(barWrap){barWrap.textContent=label;barWrap.style.color=color;}
  const scoreNum=document.getElementById('health-score-num');
  if(scoreNum){scoreNum.textContent=score+'/10';scoreNum.style.color=color;}
  if(elF){elF.innerHTML=findings.map(f=>`<p style="margin-bottom:7px;font-size:11px;color:rgba(255,255,255,0.8);line-height:1.5">• ${f}</p>`).join('');}
  if(elA){elA.innerHTML=actions.length===0
    ?'<p style="font-size:11px;color:#68D391;font-weight:600">✅ No immediate actions needed</p>'
    :actions.map(a=>`<div style="display:flex;gap:7px;margin-bottom:8px;align-items:flex-start"><span style="color:#00C2E0;flex-shrink:0;font-size:12px">→</span><p style="font-size:11px;color:rgba(255,255,255,0.8);line-height:1.5;margin:0">${a}</p></div>`).join('');}
  if(sc){sc.textContent=score;sc.style.color=color;}
}
"""
