"""Prepare a separate page from the verified owner HTML; never install it."""
import argparse
import hashlib
from pathlib import Path

EXPECTED_HTML_SHA='a9a47e0fe7d9b8139322873f27b31209862a8805296a9e5070ce7ff599069aa7'


def prepare_html(content):
    if hashlib.sha256(content).hexdigest()!=EXPECTED_HTML_SHA:
        raise ValueError('experimental page differs from verified owner version')
    text=content.decode()
    replacements=[
      ('</head>', '<link rel="stylesheet" href="/site_shell.css"><script defer src="/site_shell.js"></script><style>body{max-width:none;margin:0;padding:0}.tf-overview-wrap{max-width:1500px;margin:auto;padding:28px 4%}.tf-overview-heading{display:flex;justify-content:space-between;align-items:end;gap:18px;margin-bottom:18px}.tf-overview-heading h1{margin:.2rem 0}.tf-overview-actions{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:700px){.tf-overview-heading{display:block}.tf-overview-actions{margin-top:12px}}</style></head>'),
      ('<body>\n<p><a href="/">← Torn Fren stock graphs</a></p>\n<h1>Experimental champion predictions</h1>', '<body><a class="tf-skip" href="#main-content">Skip to content</a><header class="tf-shell"><a class="tf-brand" href="/experimental">TORN<span>-FREN</span></a><button class="tf-menu" type="button" aria-expanded="false" aria-label="Toggle navigation">☰</button><nav class="tf-nav" aria-label="Main navigation"><a data-tf-section="overview" href="/experimental">Overview</a><a data-tf-section="detail" href="/">Item detail</a><a data-tf-section="travel" href="/travel-decisions">Travel decisions</a></nav><div class="tf-shell-status"><span class="tf-beta">Beta</span></div></header><main class="tf-overview-wrap" id="main-content"><div class="tf-overview-heading"><div><div class="tf-eyebrow">Overview</div><h1>Foreign stock opportunities</h1><p class="muted">Scan modeled departures across supported items, then open the item detail or travel planner for more context.</p></div><div class="tf-overview-actions"><a class="tf-action-link" href="/">Open item detail</a><a class="tf-action-link primary" href="/travel-decisions">Plan a trip</a></div></div>'),
      ('<thead><tr><th>Item</th><th>Model</th><th>State</th><th>Departure (your time)</th><th>Arrival (your time)</th><th>Valid until</th></tr></thead>', '<thead><tr><th>Item</th><th>Model</th><th>Guidance</th><th>Leave</th><th>Land</th><th>Recheck by</th></tr></thead>'),
      ('<p class="muted">This page reads precomputed results only, refreshing every 30 seconds. It never runs a forecasting model or schedules travel.</p>\n\n<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>', '<p class="muted">This page reads precomputed results only. Forecasts can change; recheck before you travel.</p></main>\n\n<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'),
      ('refreshing every 30 seconds.', 'refreshing every 10 seconds.'),
      ('<script src="/champion_graph.js"></script>', '<script src="/champion_graph.js"></script>\n<script src="/shared_experimental_rows.js"></script>'),
      ('const fields=[', 'let sharedRawRows=[],sharedReceivedEpoch=null,sharedFetchError=false,sharedRefreshGeneration=0;\nconst fields=['),
      ('async function refresh(){', 'async function refresh(){const seq=++sharedRefreshGeneration;'),
      ('  if(!response.ok){', '  if(seq!==sharedRefreshGeneration)return;\n  if(!response.ok){'),
      ('  const result=await response.json();', '  const result=await response.json();if(seq!==sharedRefreshGeneration)return;'),
      ('v=item.actionable?"Ready · experimental":v;', 'v=item.shared_departure_preview?item.status_label:item.actionable?"Ready · experimental":v;'),
      ('new Date().toLocaleTimeString()+". "+rows.filter', '(sharedReceivedEpoch===null?"—":new Date(sharedReceivedEpoch*1000).toLocaleTimeString())+". "+rows.filter'),
      ('if(!response.ok){state.textContent=', 'if(!response.ok){sharedFetchError=true;sharedRawRows=[];paint([]);window.refreshChampionGraph([]);state.textContent='),
      ('  paint(result.latest);\n  window.refreshChampionGraph(result.latest);', '  sharedReceivedEpoch=Math.floor(Date.now()/1000);sharedFetchError=false;sharedRawRows=result.latest;\n  const visible=SharedExperimentalRows.project(sharedRawRows,sharedReceivedEpoch);\n  paint(visible);window.refreshChampionGraph(visible);'),
      ('}catch(_){state.textContent=', '}catch(_){if(seq!==sharedRefreshGeneration)return;sharedFetchError=true;sharedRawRows=[];window.refreshChampionGraph([]);state.textContent='),
      ('refresh();setInterval(refresh,30000);', 'refresh();setInterval(refresh,10000);\nsetInterval(()=>{if(sharedFetchError)return;const visible=SharedExperimentalRows.project(sharedRawRows,Math.floor(Date.now()/1000));paint(visible);window.refreshChampionGraph(visible);},1000);')]
    for old,new in replacements:
        if text.count(old)!=1:raise ValueError('owner page integration anchor changed')
        text=text.replace(old,new)
    return text


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();source=Path(a.source);output=Path(a.output)
    if source.resolve()==output.resolve() or output.is_symlink():raise ValueError('separate output required')
    output.write_text(prepare_html(source.read_bytes()))
