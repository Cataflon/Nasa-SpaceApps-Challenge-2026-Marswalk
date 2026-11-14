import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {captureSurface,restoreSurface} from '../src/terrain/layerState.js';
import {eventSpecs,eventPayload} from '../src/simulation/events.js';
import {readFileSync} from 'node:fs';
test('analytic layers restore original GLTF vertex colors and material repeatedly',()=>{
  const geometry=new THREE.BufferGeometry(),originalColor=new THREE.Float32BufferAttribute([.7,.3,.1],3);
  geometry.setAttribute('color',originalColor);const originalMaterial=new THREE.MeshStandardMaterial({vertexColors:true});
  const mesh=new THREE.Mesh(geometry,originalMaterial),snapshot=captureSurface(mesh);
  for(let n=0;n<3;n++){geometry.setAttribute('color',new THREE.Float32BufferAttribute([.1,.1,.1],3));mesh.material=new THREE.MeshStandardMaterial();restoreSurface(mesh,snapshot);assert.equal(mesh.material,originalMaterial);assert.equal(geometry.getAttribute('color'),originalColor);}
  geometry.deleteAttribute('color');const noColor=captureSurface(mesh);geometry.setAttribute('color',originalColor);restoreSurface(mesh,noColor);assert.equal(geometry.hasAttribute('color'),false);
});
test('integration examples reference defined custom stops in explicit request order',()=>{
  const schema=JSON.parse(readFileSync(new URL('../contracts/route-request-v1.1.schema.json',import.meta.url),'utf8'));
  const examples=JSON.parse(readFileSync(new URL('../contracts/examples.json',import.meta.url),'utf8'));
  const request=examples.route_request;
  for(const key of schema.required)assert.ok(Object.hasOwn(request,key),key);
  assert.equal(request.schema_version,'1.1');assert.equal(request.stop_order,'request');
  assert.equal(request.custom_stops[0].id,request.stops[1]);
  assert.deepEqual(examples.spatial_event.params,eventPayload('local_storm',{...eventSpecs.local_storm.defaults,row:220,col:260},{shape:[500,500]}));
});
test('event configuration serializes engine units and rejects invalid centers and parameters',()=>{
  const site={shape:[500,500]},values={...eventSpecs.local_storm.defaults,row:42,col:73};
  const payload=eventPayload('local_storm',values,site);
  assert.deepEqual(payload.center,{row:42,col:73});assert.deepEqual(payload.axes_m,[15000,2500]);assert.deepEqual(payload.velocity_ms,[0,15]);
  assert.throws(()=>eventPayload('local_storm',{...values,row:500},site),/inside/);
  assert.throws(()=>eventPayload('local_storm',{...values,axis_a:-1},site),/between/);
  assert.deepEqual(eventPayload('solar_particle_event',{dose_rate_multiplier:2.5,duration_min:240},site),{dose_rate_multiplier:2.5,duration_min:240});
  assert.deepEqual(eventPayload('suit_leak',{leak_pct_per_min:.15},site),{leak_pct_per_min:.15});
  assert.throws(()=>eventPayload('fatigue',{speed_factor:2},site),/between/);
});
