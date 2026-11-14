import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
test('waypoint routing visits ordered stops, returns home and measures the complete trip',()=>{
  let result;const self={postMessage:value=>{result=value;}};
  vm.runInNewContext(readFileSync(new URL('../src/terrain/routing.worker.js',import.meta.url),'utf8'),{self});
  self.onmessage({data:{type:'grid',grid:{rows:5,cols:5,cell_size_m:20,elevation:Array(25).fill(100)}}});
  self.onmessage({data:{id:1,start:{row:0,col:0},tripStops:[{row:0,col:4},{row:4,col:4},{row:0,col:0}]}});
  assert.equal(result.id,1);assert.equal(result.error,undefined);
  const path=Array.from(result.safe.path,p=>Array.from(p));
  assert.deepEqual(path[0],[0,0]);assert.deepEqual(path.at(-1),[0,0]);
  const first=path.findIndex(p=>p[0]===0&&p[1]===4),second=path.findIndex(p=>p[0]===4&&p[1]===4);
  assert.ok(first>0&&second>first);assert.ok(Math.abs(result.safe.distance-(160+80*Math.SQRT2))<1e-8);
  assert.equal(result.safe.ascent,0);assert.equal(result.safe.maxSlope,0);
  assert.equal('budget' in result.safe,false);
  self.onmessage({data:{id:2,start:{row:0,col:0},tripStops:[{row:8,col:4}]}});
  assert.match(result.error,/outside/);
});
