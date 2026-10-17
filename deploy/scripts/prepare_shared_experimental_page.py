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
