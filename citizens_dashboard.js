
var CHART_DATA={
  labels:["Oct 20", "Nov 20", "Dec 20", "Jan 20", "Feb 20", "Mar 20"],
  open:[0, 0, 3, 2, 6, 10],
  resolved:[0, 0, 0, 37, 29, 34],
  yMax:40
};
function initChart(){
  var canvas=document.getElementById('trendChart');
  if(!canvas)return;
  // In Confluence iframes offsetWidth is often 0 — walk up the DOM for a real width,
  // then fall back to a fixed 600px so bars always render.
  var W=0;
  var el=canvas;
  while(el&&W<10){W=el.offsetWidth||0;el=el.parentElement;}
  if(W<10)W=600;
  var H=canvas.parentElement?canvas.parentElement.offsetHeight||220:220;
  if(H<80)H=220;
  var dpr=window.devicePixelRatio||1;
  canvas.width=W*dpr; canvas.height=H*dpr;
  canvas.style.width=W+'px'; canvas.style.height=H+'px';
  var ctx=canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  var PAD={top:28,right:12,bottom:36,left:32};
  var n=CHART_DATA.labels.length;
  var chartW=W-PAD.left-PAD.right;
  var chartH=H-PAD.top-PAD.bottom;
  var yMax=CHART_DATA.yMax||1;
  var groupW=chartW/n;
  var barW=Math.max(4,groupW*0.32);
  var gap=groupW*0.04;
  var startTime=null;
  var DUR=900;
  function ease(t){return t<1?1-Math.pow(1-t,4):1;}
  function draw(ts){
    try{
      if(!startTime)startTime=ts;
      var prog=Math.min((ts-startTime)/DUR,1);
      ctx.clearRect(0,0,W,H);
      ctx.strokeStyle='rgba(255,255,255,0.07)';
      ctx.lineWidth=0.5;
      var steps=5;
      for(var i=0;i<=steps;i++){
        var y=PAD.top+chartH-(i/steps)*chartH;
        ctx.beginPath();ctx.moveTo(PAD.left,y);ctx.lineTo(W-PAD.right,y);ctx.stroke();
        ctx.fillStyle='rgba(255,255,255,0.45)';
        ctx.font='9px system-ui,sans-serif';
        ctx.textAlign='right';
        ctx.fillText(Math.round(yMax*i/steps),PAD.left-4,y+3);
      }
      for(var gi=0;gi<n;gi++){
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
      }
      // Legend — top left, clear of bars
      ctx.fillStyle='rgba(26,111,219,0.88)';ctx.fillRect(PAD.left,5,8,8);
      ctx.fillStyle='rgba(255,255,255,0.55)';ctx.font='9px system-ui,sans-serif';ctx.textAlign='left';ctx.fillText('Open (SR)',PAD.left+11,13);
      ctx.fillStyle='rgba(56,161,105,0.88)';ctx.fillRect(PAD.left+68,5,8,8);
      ctx.fillStyle='rgba(255,255,255,0.55)';ctx.fillText('Resolved',PAD.left+79,13);
      if(prog<1)requestAnimationFrame(draw);
    }catch(e){console.error('chart draw error:',e);}
  }
  requestAnimationFrame(draw);
}
// Fire initChart as soon as DOM is ready — works even if DOMContentLoaded already fired
if(document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded',initChart);
}else{
  initChart();
}

var DATA={"p0p1": 0, "support": 25, "features": 60, "eng_tickets": 12, "resolved": 100, "pendingEng": 5, "p0keys": [], "highKeys": ["SR-8547", "SR-8511", "SR-8499"], "generated": "Mar 28, 2026 20:18 EST", "score": 4, "scoreLabel": "Needs Attention", "scoreColor": "#FC8181"};

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

window.addEventListener('DOMContentLoaded',function(){
  try{runHealth(DATA);}catch(e){console.error('runHealth:',e);}
  try{buildHealthDrawer(DATA);}catch(e){console.error('buildHealthDrawer:',e);}

  // ── Health bar + score count-up animation ──────────────────────────────────
  var targetScore=DATA.score;
  var targetPct=targetScore*10;

  // Animate the main panel bar
  var bar=document.getElementById('health-score-bar');
  if(bar){
    setTimeout(function(){bar.style.width=targetPct+'%';},120);
  }

  // Animate the drawer bar (only exists once drawer is opened,
  // but set it preemptively in case drawer is already open)
  var dbar=document.getElementById('health-drawer-bar');
  if(dbar){
    setTimeout(function(){dbar.style.width=targetPct+'%';},120);
  }

  // Count-up the score number 0 → score over 700ms with easeOutQuart
  var numEl=document.getElementById('health-score-num');
  if(numEl){
    var start=null;
    var dur=700;
    function countUp(ts){
      if(!start)start=ts;
      var prog=Math.min((ts-start)/dur,1);
      var ease=1-Math.pow(1-prog,4);
      var cur=Math.round(ease*targetScore);
      numEl.textContent=cur+'/10';
      if(prog<1)requestAnimationFrame(countUp);
      else numEl.textContent=targetScore+'/10';
    }
    setTimeout(function(){requestAnimationFrame(countUp);},80);
  }
});
function switchTab(custId,tabId){
  var tabs=['current','engage'];
  tabs.forEach(function(t){
    var panel=document.getElementById('tab-'+t+'-'+custId);
    var btn=document.getElementById('tab-btn-'+t+'-'+custId);
    if(!panel||!btn)return;
    var active=(t===tabId);
    panel.style.display=active?'block':'none';
    btn.style.color=active?'#fff':'rgba(255,255,255,0.4)';
    btn.style.background=active?'rgba(255,255,255,0.06)':'transparent';
    btn.style.borderBottom=active?'2px solid #00C2E0':'2px solid transparent';
  });
}
function toggleDrawer(dId,mId){var d=document.getElementById(dId),m=document.getElementById(mId),open=d.classList.contains('open');document.querySelectorAll('.drawer').forEach(function(x){x.classList.remove('open');});document.querySelectorAll('.metric').forEach(function(x){x.classList.remove('active');});if(!open){d.classList.add('open');m.classList.add('active');if(dId==='drawer-health'){try{buildHealthDrawer(DATA);}catch(e){console.error('buildHealthDrawer:',e);}};  }}
function copyJql(btn,key){var el=document.getElementById('jql-'+key);if(!el)return;navigator.clipboard.writeText(el.textContent.trim()).then(function(){var orig=btn.textContent;btn.textContent='Copied!';btn.style.color='#38A169';setTimeout(function(){btn.textContent=orig;btn.style.color='';},1500);}).catch(function(){btn.textContent='Failed';setTimeout(function(){btn.textContent='Copy';},1500);});}
function buildHealthDrawer(DATA){
  var factors=[],actions=[];
  if(DATA.p0p1>=3){factors.push(['-4 pts',DATA.p0p1+' active P0 incidents ('+DATA.p0keys.join(', ')+')', '#E53E3E']);actions.push(['[P0]','Escalate to engineering leadership']);}
  else if(DATA.p0p1===2){factors.push(['-3 pts','2 P0 incidents ('+DATA.p0keys.join(', ')+')', '#E53E3E']);actions.push(['[P0]','Both need engineering owner today']);}
  else if(DATA.p0p1===1){factors.push(['-2 pts','1 active P0/P1 ('+DATA.p0keys[0]+')', '#DD6B20']);actions.push(['[P0]','Daily updates to customer until resolved']);}
  else{factors.push(['+0 pts','No active P0/P1 incidents','#38A169']);}
  if(DATA.support>=8){factors.push(['-2 pts','High SR backlog — '+DATA.support+' open','#DD6B20']);actions.push(['[SR]','Close or escalate stale SR tickets']);}
  else if(DATA.support>=5){factors.push(['-1 pt','Moderate SR backlog — '+DATA.support+' open','#D69E2E']);actions.push(['[SR]','Target 3 SR resolutions this sprint']);}
  else{factors.push(['+0 pts','Healthy SR volume — '+DATA.support+' open','#38A169']);}
  if(DATA.pendingEng>=4){factors.push(['-2 pts',DATA.pendingEng+' SR tickets blocked pending eng','#DD6B20']);actions.push(['[ENG]','Set ETAs and communicate to customer']);}
  else if(DATA.pendingEng>=2){factors.push(['-1 pt',DATA.pendingEng+' SR tickets pending engineering','#D69E2E']);actions.push(['[ENG]','Chase ETAs this week']);}
  else{factors.push(['+0 pts','No SR tickets blocked on engineering','#38A169']);}
  if(DATA.eng_tickets>=5){factors.push(['-1 pt',DATA.eng_tickets+' TS engineering tickets open','#D69E2E']);actions.push(['[TS]','Review and triage TS engineering backlog']);}
  else{factors.push(['+0 pts',DATA.eng_tickets+' TS engineering tickets','#38A169']);}
  if(DATA.features>=5){factors.push(['-1 pt',DATA.features+' TS feature requests open','#D69E2E']);actions.push(['[FR]','Schedule roadmap call']);}
  else{factors.push(['+0 pts',DATA.features+' feature requests','#38A169']);}
  if(DATA.resolved===0){factors.push(['-1 pt','No SR tickets resolved in 30d','#DD6B20']);actions.push(['[SR]','Close at least one SR ticket']);}
  else{factors.push(['+0 pts',DATA.resolved+' SR resolved in 30d','#38A169']);}
  var fEl=document.getElementById('health-factors');
  if(fEl)fEl.innerHTML=factors.map(function(r){return '<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:'+r[2]+'1A;color:'+r[2]+';flex-shrink:0;min-width:44px;text-align:center">'+r[0]+'</span><span style="font-size:11px;color:#172B4D;line-height:1.5">'+r[1]+'</span></div>';}).join('');
  var aEl=document.getElementById('health-actions');
  if(aEl)aEl.innerHTML=actions.length===0?'<p style="font-size:11px;color:#38A169;font-weight:600">No immediate actions needed</p>':actions.map(function(r){return '<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px"><span style="font-size:10px;font-weight:700;padding:2px 5px;border-radius:3px;background:#E6F1FB;color:#0C447C;flex-shrink:0">'+r[0]+'</span><span style="font-size:11px;color:#172B4D;line-height:1.5">'+r[1]+'</span></div>';}).join('');
}