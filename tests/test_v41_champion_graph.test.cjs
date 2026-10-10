const test = require("node:test");
const assert = require("node:assert/strict");
const graph = require("../web/static/champion_graph.js");

test("counts only observed zero-to-positive as restocks",()=>{
  const rows = [
    {timestamp:100,quantity:0,anchor:true},
    {timestamp:200,quantity:50},
    {timestamp:300,quantity:60},
    {timestamp:400,quantity:0},
    {timestamp:500,quantity:30}
  ];
  assert.deepEqual(graph.extractEvents(rows).map(e=>e.type),
    ["restock","increase","depletion","restock"]);
  const stats=graph.describe(graph.extractEvents(rows));
  assert.equal(stats.restockCount,2);
  assert.equal(stats.increaseCount,1);
  assert.equal(stats.depletionCount,1);
  assert.equal(stats.avgZeroToRestockSeconds,100);
  assert.equal(stats.avgStockLifetimeSeconds,200);
});

test("never counts anchored quantity as a restock",()=>{
  const events=graph.extractEvents([
    {timestamp:100,quantity:50,anchor:true},
    {timestamp:200,quantity:50},
    {timestamp:300,quantity:0}
  ]);
  assert.deepEqual(events.map(e=>e.type),["depletion"]);
  assert.equal(graph.describe(events).avgStockLifetimeSeconds,null);
});

test("does not infer cycle statistics from absence of observed transitions",()=>{
  const stats=graph.describe(graph.extractEvents([
    {timestamp:100,quantity:30,anchor:true},
    {timestamp:200,quantity:25},
    {timestamp:300,quantity:10}
  ]));
  assert.equal(stats.restockCount,0);
  assert.equal(stats.avgZeroToRestockSeconds,null);
  assert.equal(stats.avgStockLifetimeSeconds,null);
});

test("returns correct timestamp and quantity chart points",()=>{
  assert.deepEqual(graph.stockPoints([{timestamp:100,quantity:0,anchor:true}]),
    [{x:100000,y:0,anchor:true}]);
  assert.deepEqual(graph.eventPoints([{type:"restock",timestamp:200,quantity:30}],"restock"),
    [{x:200000,y:30}]);
});

test("excludes invalid rows and does not mutate original",()=>{
  const rows=[{timestamp:100,quantity:0,anchor:true},
    {timestamp:150,quantity:null}, {timestamp:200,quantity:30}];
  const events=graph.extractEvents(rows);
  assert.equal(events.length,1);
  assert.equal(events[0].type,"restock");
  assert.equal(rows.length,3);
});
