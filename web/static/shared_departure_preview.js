/* Optional graph panel and marker from the same snapshot as Travel Decisions. */
(() => {
  'use strict';
  let data=null;
  const now=()=>Math.floor(Date.now()/1000);
  const stamp=t=>new Date(t*1000).toLocaleTimeString();
  function active(){
    const row=data?.row,d=row?.decision,t=now();
    return row&&Number.isFinite(data.source_poll_age_seconds)
      &&data.source_poll_age_seconds+Math.max(0,t-data.evaluated_at_epoch)<=180
      &&t-data.asof_epoch<=660&&row.departure_epoch!==null
      &&(d.valid_until_epoch===undefined||t<=d.valid_until_epoch)
      &&(row.departure_deadline_epoch===null||t<=row.departure_deadline_epoch);
  }
  function render(){
    const panel=document.getElementById('sharedDeparturePreview');
    if(!panel)return;
    panel.hidden=!data;
    window.dispatchEvent(new Event('torn-shared-departure-tick'));
    if(!data)return;
    const row=data.row;
    let message='Selected departure estimate · Await a fresh recommendation';
    if(active()){
      const depart=row.departure_source==='explicit_recommendation'
        ?row.departure_epoch:Math.max(now(),row.departure_epoch);
      const wait=Math.max(0,depart-now());
      message=`Selected departure estimate · ${wait?`Leave in ${Math.ceil(wait/60)}m`:'Reconfirm before leaving'} · Depart ${stamp(depart)} · Land ${stamp(depart+row.decision.player_flight_seconds)}`;
    }
    panel.textContent=message;
  }
  window.sharedDeparturePreview={set(value){data=value||null;render();},clear(){data=null;render();}};
  window.addEventListener('torn-shared-departure',e=>window.sharedDeparturePreview.set(e.detail));
  setInterval(render,1000);
  if(window.Chart)Chart.register({id:'selectedDepartureEstimate',afterDraw(chart){
    if(!active()||!chart.scales?.x)return;
    const x=chart.scales.x.getPixelForValue(data.row.departure_epoch*1000),area=chart.chartArea;
    if(x<area.left||x>area.right)return;
    const ctx=chart.ctx;ctx.save();ctx.strokeStyle='#b8ef76';ctx.setLineDash([4,4]);
    ctx.beginPath();ctx.moveTo(x,area.top);ctx.lineTo(x,area.bottom);ctx.stroke();
    ctx.fillStyle='#b8ef76';ctx.fillText('Departure estimate',Math.min(x+5,area.right-110),area.top+14);ctx.restore();
  }});
})();
