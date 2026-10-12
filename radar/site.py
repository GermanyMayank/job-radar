"""Builds docs/index.html: one self-contained, dependency-free page served by GitHub Pages.
All data is embedded, so the page needs a single request and works offline once loaded.
Only open jobs are published (status new/apply); tracker notes never leave the repo."""
import json
import os
from datetime import date

SOURCE_NAMES = {"bundesagentur": "Bundesagentur", "adzuna": "Adzuna", "jooble": "Jooble",
                "arbeitnow": "Arbeitnow", "watchlist": "Company site", "linkedin": "LinkedIn"}


def _payload(jobs, tracker_rows):
    today = date.today().isoformat()
    out = []
    for j in jobs:
        row = tracker_rows.get(j.key, {})
        if row.get("status", "new") not in ("new", "apply"):
            continue
        out.append({
            "s": j.score, "b": j.bucket, "t": j.title, "c": j.company or "", "l": j.location or "",
            "p": j.posted or "", "src": [SOURCE_NAMES.get(x, x.title()) for x in j.sources],
            "why": j.reasons, "warn": j.flags, "u": j.url, "a": j.apply_url or "",
            "n": row.get("first_seen") == today, "ap": row.get("status") == "apply",
        })
    return out


def write_site(jobs, tracker_rows, out_dir, run_stats):
    os.makedirs(out_dir, exist_ok=True)
    data = {"date": date.today().isoformat(), "scanned": run_stats.get("raw", 0),
            "jobs": _payload(jobs, tracker_rows)}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(TEMPLATE.replace("__DATA__", blob))
    open(os.path.join(out_dir, ".nojekyll"), "w").close()   # serve as-is, skip GitHub's Jekyll build


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>Job Radar</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%E2%98%80%EF%B8%8F%3C/text%3E%3C/svg%3E">
<style>
:root{--bg:#F5F8FB;--panel:#FFFFFF;--ink:#13233A;--muted:#5E6E85;--line:#DCE3EC;--cell:#1F4E8C;--cell-empty:#E3EAF3;--sun:#F2B705;--warn:#9A5B00;--focus:#F2B705}
@media (prefers-color-scheme:dark){:root{--bg:#0E1A2B;--panel:#13233A;--ink:#E8EEF6;--muted:#9AAAC0;--line:#24364F;--cell:#5B8FD6;--cell-empty:#1B2C44;--sun:#F7C948;--warn:#F2C26B}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom)}
.wrap{max-width:860px;margin:0 auto;padding:0 18px}
header.wrap{padding-top:36px;padding-bottom:18px}
h1{font-size:clamp(28px,6vw,40px);line-height:1.1;margin:0 0 10px;letter-spacing:-.02em;font-weight:750}
h1 .date{display:block;font-size:.45em;font-weight:500;color:var(--muted);letter-spacing:0;margin-top:6px}
.lead{margin:0;color:var(--muted);max-width:62ch}
.lead b{color:var(--ink)}
.bar{position:sticky;top:0;z-index:2;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:12px 0}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
input[type=search],select{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 12px;min-height:42px}
input[type=search]{flex:1 1 220px}
.chip{font:inherit;font-size:15px;color:var(--ink);background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:8px 14px;min-height:42px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.count{font-size:14px;color:var(--muted);margin:14px 0 4px}
ol{list-style:none;margin:0;padding:0}
li.job{display:grid;grid-template-columns:56px 1fr;gap:16px;padding:18px 0;border-bottom:1px solid var(--line)}
.cell{width:56px;height:64px;border-radius:6px;background:linear-gradient(to top,var(--cell) var(--fill),var(--cell-empty) var(--fill));display:flex;align-items:center;justify-content:center;font-weight:750;font-size:21px;font-variant-numeric:tabular-nums;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.35);position:relative}
.cell.low{color:var(--ink);text-shadow:none}
.cell::after{content:"";position:absolute;inset:0;border-radius:6px;background-image:linear-gradient(90deg,transparent 49%,rgba(255,255,255,.18) 49% 51%,transparent 51%),linear-gradient(0deg,transparent 32%,rgba(255,255,255,.18) 32% 34%,transparent 34% 65%,rgba(255,255,255,.18) 65% 67%,transparent 67%)}
.cell.strong{box-shadow:0 0 0 2px var(--sun)}
.t{font-size:18px;font-weight:650;line-height:1.3;margin:0}
.t a{color:inherit;text-decoration:none}
.t a:hover{text-decoration:underline}
.new{display:inline-block;font-size:12px;font-weight:650;background:var(--sun);color:#13233A;border-radius:4px;padding:1px 6px;margin-left:6px;vertical-align:2px}
.meta{color:var(--muted);margin:2px 0 6px}
.why{margin:0;font-size:15px}
.warn{margin:4px 0 0;font-size:15px;color:var(--warn)}
.links{margin-top:8px;display:flex;gap:16px;font-size:15px}
.links a{color:var(--cell);font-weight:600}
.empty{padding:48px 0;color:var(--muted)}
footer.wrap{color:var(--muted);font-size:14px;padding-top:28px;padding-bottom:40px}
@media (max-width:520px){li.job{grid-template-columns:46px 1fr;gap:12px}.cell{width:46px;height:54px;font-size:18px}.t{font-size:17px}}
</style>
</head>
<body>
<header class="wrap">
  <h1>Today's solar PM jobs<span class="date" id="date"></span></h1>
  <p class="lead" id="lead"></p>
</header>
<div class="bar"><div class="wrap controls" role="search">
  <input type="search" id="q" placeholder="Search jobs" aria-label="Search jobs">
  <button class="chip" id="strong" aria-pressed="false">Strong only</button>
  <button class="chip" id="fresh" aria-pressed="false">New today</button>
  <select id="src" aria-label="Source"><option value="">All sources</option></select>
</div></div>
<main class="wrap">
  <p class="count" id="count" aria-live="polite"></p>
  <ol id="list"></ol>
</main>
<footer class="wrap">Updated every morning by the job radar. Scores sort jobs by fit with Mayank's CV; always read the posting before applying.</footer>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  var D=JSON.parse(document.getElementById('data').textContent), J=D.jobs;
  var $=function(id){return document.getElementById(id)};
  var esc=function(s){return String(s||'').replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})};
  var nice=function(iso){if(!iso)return'';var d=new Date(iso+'T12:00:00');return d.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'})};
  var strong=J.filter(function(j){return j.b==='Strong'}).length, fresh=J.filter(function(j){return j.n}).length;
  $('date').textContent=nice(D.date);
  $('lead').innerHTML='<b>'+strong+' strong '+(strong===1?'match':'matches')+'</b> out of '+J.length+' open jobs, '+fresh+' new today. Picked from '+D.scanned.toLocaleString('en-GB')+' postings.';
  var srcs={};J.forEach(function(j){j.src.forEach(function(s){srcs[s]=1})});
  Object.keys(srcs).sort().forEach(function(s){var o=document.createElement('option');o.value=s;o.textContent=s;$('src').appendChild(o)});
  var st={q:'',strong:false,fresh:false,src:''};
  function toggle(btn,key){btn.addEventListener('click',function(){st[key]=!st[key];btn.setAttribute('aria-pressed',st[key]);draw()})}
  toggle($('strong'),'strong');toggle($('fresh'),'fresh');
  $('q').addEventListener('input',function(e){st.q=e.target.value.toLowerCase();draw()});
  $('src').addEventListener('change',function(e){st.src=e.target.value;draw()});
  function row(j){
    var meta=[j.c,j.l].filter(Boolean).join(', ')+(j.p?' \u2013 posted '+nice(j.p).replace(/^\w+, /,''):'');
    var links='<a href="'+esc(j.u)+'" target="_blank" rel="noopener">Open posting</a>'+(j.a?'<a href="'+esc(j.a)+'" target="_blank" rel="noopener">Apply</a>':'');
    return '<li class="job"><div class="cell'+(j.b==='Strong'?' strong':'')+(j.s<45?' low':'')+'" style="--fill:'+j.s+'%" title="Fit score '+j.s+' of 100">'+j.s+'</div>'+
      '<div><p class="t"><a href="'+esc(j.u)+'" target="_blank" rel="noopener">'+esc(j.t)+'</a>'+(j.n?'<span class="new">New</span>':'')+'</p>'+
      '<p class="meta">'+esc(meta)+'</p>'+
      (j.why.length?'<p class="why">'+esc(j.why.join(', '))+'</p>':'')+
      (j.warn.length?'<p class="warn">Check: '+esc(j.warn.join(', '))+'</p>':'')+
      '<div class="links">'+links+'</div></div></li>';
  }
  function draw(){
    var list=J.filter(function(j){
      if(st.strong&&j.b!=='Strong')return false;
      if(st.fresh&&!j.n)return false;
      if(st.src&&j.src.indexOf(st.src)<0)return false;
      if(st.q&&(j.t+' '+j.c+' '+j.l).toLowerCase().indexOf(st.q)<0)return false;
      return true});
    $('count').textContent=list.length+' of '+J.length+' jobs shown';
    $('list').innerHTML=list.length?list.map(row).join(''):'<li class="empty">No jobs match these filters. Clear the search or switch a filter off.</li>';
  }
  draw();
})();
</script>
</body>
</html>
"""
