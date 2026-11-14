import {test} from 'node:test';
import assert from 'node:assert/strict';
import {elevationAt,slopeAt,terrainProfile,scaleDistance} from '../src/terrain/explorer.js';
const flat={rows:3,cols:3,cell_size_m:20,elevation:Array(9).fill(-2500)};
test('source interpolation follows the exact two mesh triangles',()=>{const grid={rows:2,cols:2,cell_size_m:20,elevation:[0,10,20,100]};assert.equal(elevationAt(grid,.25,.25),7.5);assert.equal(elevationAt(grid,.75,.75),57.5);assert.equal(elevationAt(grid,1,1),100);assert.equal(elevationAt(grid,-1,0),null);});
test('derived slope is zero on a flat plane and uses unexaggerated meters',()=>{assert.equal(slopeAt(flat,1,1),0);const ramp={...flat,elevation:[0,20,40,0,20,40,0,20,40]};assert.ok(Math.abs(slopeAt(ramp,1,1)-45)<1e-8);});
test('profile preserves source elevations and distance endpoints',()=>{const profile=terrainProfile(flat,[[0,0],[0,2],[2,2]]);assert.equal(profile[0].distance_m,0);assert.equal(profile.at(-1).distance_m,80);assert.deepEqual([profile.at(-1).row,profile.at(-1).col],[2,2]);assert.ok(profile.every(p=>p.elevation_m===-2500));});
test('invalid or degenerate routes never become plausible profiles',()=>{assert.deepEqual(terrainProfile(flat,[[0,0],[4,4]]),[]);assert.deepEqual(terrainProfile(flat,[[1,1],[1,1]]),[]);assert.deepEqual(terrainProfile(null,[[0,0],[1,1]]),[]);});
test('projection-derived scale has the requested pixel limit',()=>{for(const ppm of [.001,.1,2,10]){const result=scaleDistance(ppm,80);assert.ok(result.pixels>0&&result.pixels<=80);assert.ok(Math.abs(result.pixels/result.meters-ppm)<1e-9);}assert.equal(scaleDistance(0),null);});
