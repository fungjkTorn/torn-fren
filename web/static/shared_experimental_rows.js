/* Never renew cached row deadlines while refreshing the display. */
window.SharedExperimentalRows={project(rows,now){
 return (Array.isArray(rows)?rows:[]).map(original=>{
  const row={...original};
  if(!Number.isFinite(row.valid_until)||now>row.valid_until){
   row.actionable=false;row.departure=null;row.arrival=null;
   row.status='EXPIRED_RECHECK_REQUIRED';
   row.status_label='Await a fresh recommendation';return row;
  }
  if(row.shared_departure_preview&&row.actionable&&row.departure!==null){
   if(row.publication_tolerance_seconds){row.departure=Math.max(now,row.departure);row.arrival=row.departure+row.flight_seconds;}
   const wait=row.departure-now;
   row.status_label=wait<=0?'Reconfirm before leaving':`Leave in ${Math.ceil(wait/60)}m`;
  }
  return row;
 });
}};
