import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { loadTerrain } from '../api/client';
import { number } from '../utils';
import Icon from './Icon';

function clear(group) {
  for (const object of [...group.children]) { group.remove(object); object.traverse(o => { o.geometry?.dispose(); if(o.material) (Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose()); }); }
}
export default function TerrainView({ site, route, live, position, selected, onSelect, compact = false }) {
  const host=useRef(null),engine=useRef(null),labels=useRef(new Map()),latest=useRef({site,selected,onSelect,position});
  latest.current={site,selected,onSelect,position};
  const [error,setError]=useState(''),[ready,setReady]=useState(false),[scale,setScale]=useState(1),[view,setView]=useState('top');
  const [comparison,setComparison]=useState(null),[planning,setPlanning]=useState(false),[activeRoute,setActiveRoute]=useState('safe');
  const worker=useRef(null),requestId=useRef(0);
  const poi=[{...site.habitat,id:'habitat',name:'Habitat',kind:'habitat'},...site.targets];
  if(selected&&!poi.some(p=>p.id===selected.id))poi.push(selected);
  if(position)poi.push({...position,id:'astronaut',name:'Astronaut',kind:'astronaut'});

  useEffect(()=>{
    let disposed=false,renderer,controls,observer,frame;
    const scene=new THREE.Scene();scene.background=new THREE.Color('#100d0b');
    const camera=new THREE.PerspectiveCamera(43,1,10,100000);
    const overlays=new THREE.Group(),landmarks=new THREE.Group();scene.add(overlays,landmarks);
    const localWorker=new Worker(new URL('../terrain/routing.worker.js',import.meta.url),{type:'module'});worker.current=localWorker;
    localWorker.onmessage=({data})=>{if(!disposed&&data.id===requestId.current){setComparison(data);setPlanning(false);}};
    localWorker.onerror=()=>{if(!disposed){setPlanning(false);setComparison({error:'Calculul local nu a putut fi finalizat.'});}};
    loadTerrain().then(async({grid,model})=>{
      const gltf=await new GLTFLoader().parseAsync(model,'');
      if(disposed){gltf.scene.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});return;}
      scene.add(gltf.scene);let display={verticalScale:1,baseThickness:0};
      let surface;
      gltf.scene.traverse(o=>{if(Number.isFinite(o.userData?.verticalScale)){display=o.userData;surface=o;}});
      if(!surface)throw Error('Modelul nu conține suprafața georeferențiată.');
      setScale(display.verticalScale);
      // Interpolare pe triangulația mesh-ului la rezoluția nativă de 20 m.
      function point(row,col,offset=45){const r=Math.max(0,Math.min(grid.rows-1,row)),c=Math.max(0,Math.min(grid.cols-1,col));const r0=Math.min(Math.floor(r),grid.rows-2),c0=Math.min(Math.floor(c),grid.cols-2),fr=r-r0,fc=c-c0,z=grid.elevation;
        const a=z[r0*grid.cols+c0],b=z[r0*grid.cols+c0+1],d=z[(r0+1)*grid.cols+c0],e=z[(r0+1)*grid.cols+c0+1];
        const elevation=fr+fc<=1?a+(b-a)*fc+(d-a)*fr:e+(d-e)*(1-fc)+(b-e)*(1-fr);
        return new THREE.Vector3((c-grid.cols/2)*grid.cell_size_m,display.baseThickness+(elevation-grid.referenceElevation)*display.verticalScale+offset,(r-grid.rows/2)*grid.cell_size_m);
      }
      scene.add(new THREE.HemisphereLight(0xffdfc0,0x332014,2.2));
      const key=new THREE.DirectionalLight(0xffd9ac,3.4);key.position.set(-8000,6500,-4000);scene.add(key);
      const fill=new THREE.DirectionalLight(0xffa56b,.75);fill.position.set(4000,3000,7000);scene.add(fill);
      renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});renderer.setPixelRatio(Math.min(devicePixelRatio,compact?1.5:2));renderer.outputColorSpace=THREE.SRGBColorSpace;
      renderer.domElement.setAttribute('aria-label','Relief 3D Jezero. Selectează punctele etichetate sau un loc pe teren.');host.current.appendChild(renderer.domElement);
      controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.08;controls.minDistance=800;controls.maxDistance=32000;controls.minPolarAngle=.02;controls.maxPolarAngle=Math.PI*.48;
      const center=new THREE.Vector3(0,display.baseThickness+700,0);controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(0,19000,35));controls.update();
      const state={grid,scene,camera,controls,overlays,landmarks,display,point,surface,renderer,flight:null,follow:false};engine.current=state;
      localWorker.postMessage({type:'grid',grid});
      controls.addEventListener('start',()=>{state.flight=null;state.follow=false;setView('free');});
      observer=new ResizeObserver(()=>{if(!host.current)return;const {width,height}=host.current.getBoundingClientRect();if(!width||!height)return;renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();overlays.traverse(o=>{if(o.material?.resolution)o.material.resolution.set(width,height);});});observer.observe(host.current);
      let down;
      renderer.domElement.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY};});
      renderer.domElement.addEventListener('pointerup',e=>{if(!down||Math.hypot(e.clientX-down.x,e.clientY-down.y)>6)return;down=null;const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);const hit=ray.intersectObject(surface,true)[0];if(!hit)return;const col=Math.round(hit.point.x/grid.cell_size_m+grid.cols/2),row=Math.round(hit.point.z/grid.cell_size_m+grid.rows/2);if(row<0||col<0||row>=grid.rows||col>=grid.cols)return;const target={id:`point_${row}_${col}`,name:'Punct ales',row,col,kind:'custom',image:null,science_value:0,dwell_min:0};latest.current.onSelect(target);});
      const projected=new THREE.Vector3();
      function animate(now){frame=requestAnimationFrame(animate);if(state.flight){const f=state.flight,t=Math.min(1,(now-f.start)/f.duration),e=t*t*(3-2*t);camera.position.lerpVectors(f.from,f.to,e);controls.target.lerpVectors(f.targetFrom,f.targetTo,e);if(t===1)state.flight=null;}
        if(state.follow&&latest.current.position){const p=point(latest.current.position.row,latest.current.position.col);const delta=p.clone().sub(controls.target).multiplyScalar(.07);camera.position.add(delta);controls.target.add(delta);}controls.update();
        for(const [id,element] of labels.current){if(!element)continue;const data=id==='astronaut'?latest.current.position:id==='habitat'?latest.current.site.habitat:latest.current.site.targets.find(t=>t.id===id)??(latest.current.selected?.id===id?latest.current.selected:null);if(!data){element.style.visibility='hidden';continue;}projected.copy(point(data.row,data.col,150)).project(camera);element.style.visibility=projected.z>-1&&projected.z<1&&Math.abs(projected.x)<1.1&&Math.abs(projected.y)<1.1?'visible':'hidden';element.style.left=`${(projected.x*.5+.5)*host.current.clientWidth}px`;element.style.top=`${(-projected.y*.5+.5)*host.current.clientHeight}px`;}
        renderer.render(scene,camera);
      }animate(performance.now());setReady(true);
    }).catch(e=>{if(!disposed)setError(e.message);});
    return()=>{disposed=true;localWorker.terminate();worker.current=null;cancelAnimationFrame(frame);observer?.disconnect();controls?.dispose();clear(scene);renderer?.dispose();renderer?.domElement.remove();engine.current=null;};
  },[site.site_id,compact]);

  function fly(mode,target){const e=engine.current;if(!e)return;const {camera,controls,point,display}=e;e.follow=false;let center,distance,offset;
    if(mode==='top'){center=new THREE.Vector3(0,display.baseThickness+700,0);offset=new THREE.Vector3(0,19000,35);}
    else {const goal=target??selected??site.targets[0],from=point(site.habitat.row,site.habitat.col),to=point(goal.row,goal.col);center=from.clone().lerp(to,.55);distance=Math.max(2800,from.distanceTo(to)*1.6);offset=new THREE.Vector3(distance*.7,distance*.48,distance*.9);}
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reduced){camera.position.copy(center).add(offset);controls.target.copy(center);controls.update();}else e.flight={from:camera.position.clone(),to:center.clone().add(offset),targetFrom:controls.target.clone(),targetTo:center,start:performance.now(),duration:1500};setView(mode);
  }
  useEffect(()=>{if(!ready)return;if(!selected){requestId.current++;setComparison(null);setPlanning(false);return;}fly('route',selected);if(!compact){const stage=host.current?.closest('.map-stage'),bounds=stage?.getBoundingClientRect();if(bounds&&(bounds.top<25||bounds.bottom>window.innerHeight))stage.scrollIntoView({block:'center',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}if(selected.id==='habitat'){requestId.current++;setComparison(null);setPlanning(false);return;}setPlanning(true);setComparison(null);setActiveRoute('safe');worker.current.postMessage({id:++requestId.current,start:site.habitat,goal:{row:Math.round(selected.row),col:Math.round(selected.col)}});},[ready,selected?.id]);

  useEffect(()=>{
    const e=engine.current;if(!ready||!e)return;clear(e.overlays);const {point,overlays,renderer}=e;
    function line(path,color,width=3,dashed=false){if(!path?.length||path.length<2)return;const xyz=[];for(let i=0;i<path.length-1;i++){const a=path[i],b=path[i+1],n=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])));for(let j=0;j<n;j++){const p=point(a[0]+(b[0]-a[0])*j/n,a[1]+(b[1]-a[1])*j/n);xyz.push(p.x,p.y,p.z);}}const end=point(...path.at(-1));xyz.push(end.x,end.y,end.z);const geometry=new LineGeometry();geometry.setPositions(xyz);const material=new LineMaterial({color,linewidth:width,depthTest:false,dashed,dashSize:100,gapSize:70});const size=renderer.getSize(new THREE.Vector2());material.resolution.copy(size);const object=new Line2(geometry,material);object.computeLineDistances();object.renderOrder=3;overlays.add(object);}
    line(route?.path,0x9d8e82,2,true);
    if(comparison&&!comparison.error){for(const key of ['short','safe'])if(comparison[key])line(comparison[key].path,key===activeRoute?0xff964e:0xc3c1b3,key===activeRoute?4:2,key!==activeRoute);}
    line(live.trail,0xb9764b,2);line(live.tick?.remaining_path,0xffb477,4);
    const chosen=live.decision?.alternative_id;for(const a of live.decision?.alternatives??[])line(a.path,!a.valid?0xf48383:a.id===chosen?0xff964e:0xbcb8a3,a.id===chosen?4:2,!a.valid);
    for(const hazard of live.tick?.hazards??[]) {const curve=(h,color,width)=>{const pts=Array.from({length:81},(_,i)=>{const a=i/80*Math.PI*2,x=Math.cos(a)*h.axes_m[0]/site.cell_size_m,y=Math.sin(a)*h.axes_m[1]/site.cell_size_m,angle=(hazard.angle_deg??0)*Math.PI/180;return [h.center.row+x*Math.sin(angle)+y*Math.cos(angle),h.center.col+x*Math.cos(angle)-y*Math.sin(angle)];});line(pts,color,width,true);};curve(hazard,0xf29d66,3);for(const f of hazard.forecast??[])curve(f,0x9b7557,1);}
  },[ready,route,live.tick,live.decision,comparison,activeRoute]);

  useEffect(()=>{const e=engine.current;if(!ready||!e)return;clear(e.landmarks);const {landmarks,point}=e;
    function add(mesh,p){mesh.position.add(p);landmarks.add(mesh);return mesh;}
    const p=point(site.habitat.row,site.habitat.col,0),white=new THREE.MeshStandardMaterial({color:0xe6ded1,roughness:.7});
    const platform=new THREE.Mesh(new THREE.CylinderGeometry(150,170,35,24),new THREE.MeshStandardMaterial({color:0x514235}));add(platform,p);
    const dome=new THREE.Mesh(new THREE.SphereGeometry(105,24,14,0,Math.PI*2,0,Math.PI/2),white);dome.position.y=18;add(dome,p);
    const pod=new THREE.Mesh(new THREE.BoxGeometry(100,90,125),white.clone());pod.position.set(115,52,0);add(pod,p);
    for(const t of site.targets){const q=point(t.row,t.col,5),ring=new THREE.Mesh(new THREE.TorusGeometry(selected?.id===t.id?90:65,10,8,32),new THREE.MeshBasicMaterial({color:selected?.id===t.id?0xff964e:0xd7c9ae}));ring.rotation.x=Math.PI/2;add(ring,q);const pole=new THREE.Mesh(new THREE.CylinderGeometry(6,6,130,8),new THREE.MeshBasicMaterial({color:0xffa565}));pole.position.y=65;add(pole,q);}
    if(selected?.kind==='custom'){const marker=new THREE.Mesh(new THREE.ConeGeometry(55,110,12),new THREE.MeshBasicMaterial({color:0xff964e}));marker.rotation.z=Math.PI;marker.position.y=150;add(marker,point(selected.row,selected.col));}
    if(position){const astronaut=new THREE.Mesh(new THREE.SphereGeometry(38,16,12),new THREE.MeshBasicMaterial({color:0xffc18c}));add(astronaut,point(position.row,position.col,65));}
  },[ready,site,selected,position]);
  const current=comparison?.[activeRoute];
  return <div className="terrain-view mission-terrain">
    <div ref={host} className="terrain-canvas"/>
    {!ready&&<div className="terrain-message">{error||'Se pregătește relieful Jezero la rezoluție completă…'}</div>}
    <div className="terrain-toolbar" aria-label="Camera 3D"><button aria-pressed={view==='top'} onClick={()=>fly('top')} disabled={!ready}><Icon name="map" size={15}/>De sus</button><button aria-pressed={view==='route'} onClick={()=>fly('route')} disabled={!ready}><Icon name="compass" size={15}/>Perspectivă traseu</button><button onClick={()=>{if(engine.current){engine.current.flight=null;engine.current.follow=!engine.current.follow;setView('follow');}}} disabled={!position}><Icon name="target" size={15}/>Urmărește</button></div>
    <div className="terrain-labels">{poi.map((p,i)=><button key={p.id} ref={el=>{if(el)labels.current.set(p.id,el);else labels.current.delete(p.id);}} className={`terrain-pin ${p.kind==='habitat'?'habitat-pin':''} ${selected?.id===p.id?'selected':''}`} onClick={()=>{if(p.id!=='astronaut')onSelect(p);}} aria-label={`Selectează ${p.name}`} aria-pressed={selected?.id===p.id}><span className="pin-dot"/>{p.kind==='habitat'?'Habitat / Baza Jezero':p.id==='astronaut'?'Astronaut':`${String(i).padStart(2,'0')} / ${p.name.split(',')[0]}`}</button>)}</div>
    <div className="terrain-compass">N<Icon name="arrow" size={17}/></div>
    {selected&&<section className="traverse-card" aria-live="polite"><div className="traverse-heading"><span>Habitat <span className="muted">/</span> {selected.name.split(',')[0]}</span><button onClick={()=>{onSelect(null);fly('top');}} aria-label="Închide selecția"><Icon name="close" size={15}/></button></div><p className="traverse-caption">Previzualizare pe relief · altitudini USGS originale</p>{planning?<p className="small">Se compară variantele de traseu…</p>:comparison?.error?<p className="error">{comparison.error}</p>:selected.id==='habitat'?<p className="small">Punct de plecare și întoarcere al misiunii.</p>:<><div className="traverse-choices">{[['safe','Pantă ponderată'],['short','Distanță minimă']].map(([key,label])=><button key={key} aria-pressed={activeRoute===key} disabled={!comparison?.[key]} onClick={()=>setActiveRoute(key)}><i className={key}/>{label}</button>)}</div>{current?<div className="traverse-stats"><div><span>Distanță</span><strong>{number(current.distance/1000,2)} km</strong></div><div><span>Urcare</span><strong>{number(current.ascent)} m</strong></div><div><span>Pantă max.</span><strong>{number(current.maxSlope,1)}°</strong></div></div>:<p className="small">Niciun traseu în limita locală de pantă de 25°.</p>}<p className="traverse-disclaimer">Fără buget O₂ sau validare de pericole. Planul misiunii este calculat separat.</p></>}</section>}
    <div className="terrain-footer"><span>USGS CTX / 20 m · 250.000 vârfuri · vertical {scale}×</span><span>Rotire: trage · Zoom: rotiță · Selectare: clic pe teren</span></div>
  </div>;
}
