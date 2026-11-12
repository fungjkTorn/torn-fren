/* Canary-only bridge for the untouched upstream V2 graph HTML. */
(()=>{
 const original=window.fetch.bind(window);let generation=0;
 window.fetch=async(input,options)=>{
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  const history=url.origin===location.origin&&url.pathname==='/api/history';
  const seq=history?++generation:0;
  if(history)window.sharedDeparturePreview.clear();
  try{
   const response=await original(input,options);
   if(history)response.clone().json().then(data=>{
    if(seq===generation)window.sharedDeparturePreview.set(data.analysis?.shared_departure_preview||null);
   }).catch(()=>{if(seq===generation)window.sharedDeparturePreview.clear();});
   return response;
  }catch(error){if(history&&seq===generation)window.sharedDeparturePreview.clear();throw error;}
 };
})();
