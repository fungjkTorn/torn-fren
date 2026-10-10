/* Observational events and lightweight chart data: no model computation. */
(function(root) {
  "use strict";
  function extractEvents(rows) {
    const events = [];
    let previous = null;
    for (const row of Array.isArray(rows) ? rows : []) {
      const timestamp = Number(row?.timestamp);
      const quantity = Number(row?.quantity);
      if (!Number.isFinite(timestamp) || !Number.isFinite(quantity) || timestamp <= 0 || quantity < 0) continue;
      if (previous && timestamp > previous.timestamp && !row.anchor) {
        if (previous.quantity === 0 && quantity > 0) {
          events.push({type: "restock", timestamp, quantity});
        } else if (previous.quantity > 0 && quantity === 0) {
          events.push({type: "depletion", timestamp, quantity});
        } else if (quantity > previous.quantity) {
          events.push({type: "increase", timestamp, quantity});
        }
      }
      previous = {timestamp, quantity};
    }
    return events;
  }
  function describe(events) {
    let lastDepletion = null, lastRestock = null;
    const waits = [], lifetimes = [];
    let restockCount = 0, depletionCount = 0, increaseCount = 0;
    for (const event of events) {
      if (event.type === "restock") {
        restockCount++;
        if (lastDepletion !== null && event.timestamp > lastDepletion) {
          waits.push(event.timestamp - lastDepletion);
        }
        lastRestock = event.timestamp;
      } else if (event.type === "depletion") {
        depletionCount++;
        if (lastRestock !== null && event.timestamp > lastRestock) {
          lifetimes.push(event.timestamp - lastRestock);
        }
        lastDepletion = event.timestamp;
      } else if (event.type === "increase") increaseCount++;
    }
    const mean = values => values.length ?
      Math.round(values.reduce((a,b) => a+b, 0) / values.length) : null;
    return {
      restockCount, depletionCount, increaseCount,
      lastRestock, lastDepletion,
      avgZeroToRestockSeconds: mean(waits),
      avgStockLifetimeSeconds: mean(lifetimes),
      waitSampleCount: waits.length, lifetimeSampleCount: lifetimes.length
    };
  }
  function stockPoints(rows) {
    return (Array.isArray(rows) ? rows : []).filter(
      r => Number.isFinite(Number(r.timestamp)) && Number.isFinite(Number(r.quantity))
    ).map(r => ({x:Number(r.timestamp)*1000,y:Number(r.quantity),anchor:Boolean(r.anchor)}));
  }
  function eventPoints(events, type) {
    return events.filter(e => e.type === type).map(e => ({x:e.timestamp*1000,y:e.quantity}));
  }
  const API = {extractEvents,describe,stockPoints,eventPoints};
  root.ChampionGraph = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : globalThis);
