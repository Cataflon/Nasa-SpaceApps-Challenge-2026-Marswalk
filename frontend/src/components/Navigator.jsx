import { lazy, Suspense, useEffect, useState } from 'react';
import Icon from './Icon';
import { decisions, number } from '../utils';
import { routeFrame } from '../terrain/navigation';
import EVAWatch from './EVAWatch';
const TerrainView=lazy(()=>import('./TerrainView'));
export default function Navigator({ site, route, live, position, selected, onSelect, navigationRoute }) {
  const [watch,setWatch]=useState(false),[progress,setProgress]=useState(0),[playing,setPlaying]=useState(false);
  const local=navigationRoute?.targetId===selected?.id?navigationRoute:null;
  const inMission=['running','paused'].includes(live.state)&&live.tick?.remaining_path?.length>1;
  const path=inMission?live.tick.remaining_path:local?.path??route?.path;
  const frame=routeFrame(path,progress,inMission?position:null);
  const destination=inMission?'Traseu live':local?.name??(route?'Traseul misiunii':'Nicio destinație');
  const bearing=frame?.heading;
  const directions=['N','NE','E','SE','S','SV','V','NV'];
  const direction=Number.isFinite(bearing)?directions[Math.round(bearing/45)%8]:'—';
  useEffect(()=>{setProgress(0);setPlaying(false);},[local?.targetId,local?.kind,route?.route_id]);
  useEffect(()=>{if(!playing||inMission||!frame)return;const timer=setInterval(()=>setProgress(p=>{const next=Math.min(1,p+20/Math.max(1,frame.total*site.cell_size_m));if(next===1)setPlaying(false);return next;}),100);return()=>clearInterval(timer);},[playing,inMission,frame?.total,site.cell_size_m]);
  const step=meters=>setProgress(p=>Math.max(0,Math.min(1,p+meters/Math.max(1,(frame?.total??1)*site.cell_size_m))));
  return <div className="navigator-page tracker-page"><div className="page-heading"><div><span className="eyebrow">Echipament de teren / EVA</span><h1>Navigatorul astronautului</h1></div><div className="segmented"><button aria-pressed={!watch} onClick={()=>setWatch(false)}>Tracker</button><button aria-pressed={watch} onClick={()=>setWatch(true)}>Ceas</button></div></div>
    {watch?<EVAWatch site={site} route={route} live={live} position={position} path={path} frame={frame} progress={progress} setProgress={setProgress} playing={playing} setPlaying={setPlaying}/>:
    <div className="tracker-layout"><section className="field-tracker" aria-label="Tracker EVA robust cu vizualizare first person">
      <i className="tracker-screw top-left"/><i className="tracker-screw top-right"/><i className="tracker-screw bottom-left"/><i className="tracker-screw bottom-right"/>
      <div className="tracker-crown"><span className="tracker-maker">MARSWALK <small>EVA FIELD UNIT</small></span><span className="tracker-led"/><span className="tracker-serial">MRK / 04</span></div>
      <div className="tracker-sidekeys"><button aria-label="Înapoi 50 metri în previzualizare" disabled={inMission||!frame} onClick={()=>step(-50)}>−</button><button aria-label="Înainte 50 metri în previzualizare" disabled={inMission||!frame} onClick={()=>step(50)}>+</button></div>
      <div className="tracker-screen"><header className="tracker-screen-status"><span><i/>{inMission?'SIMULARE LIVE':'PREVIZUALIZARE'}</span><span>VIZOR / FPV</span><Icon name="shield" size={14}/></header>
      <div className="tracker-bearing"><span>{direction}</span><div className="bearing-ticks"/><strong>{number(bearing)}°</strong></div>
      {path?.length>1?<Suspense fallback={<p className="terrain-message">Se încarcă vizorul…</p>}><TerrainView key={`fp-${site.site_id}`} site={site} route={route} live={live} position={position} selected={selected} onSelect={onSelect} compact firstPerson navigationPath={path} navigationProgress={progress} navigationLive={inMission}/></Suspense>:<div className="tracker-empty"><Icon name="compass" size={44}/><h2>Alege un traseu</h2><p>Selectează un punct în pagina Misiune și alege varianta de traseu.</p></div>}
      <div className="tracker-reticle" aria-hidden="true"><span/><i/><span/></div>
      <div className="tracker-destination"><Icon name="arrow" size={22}/><div><span>Destinație</span><strong>{destination?.split(',')[0]}</strong></div><b>{number(frame?.remaining*site.cell_size_m/1000,2)}<small> km</small></b></div>
      <div className="tracker-vitals"><div><span>O₂</span><strong>{number(live.tick?.sensors?.o2_pct,1)}<small>%</small></strong></div><div><span>Decizie</span><strong>{decisions[live.decision?.decision]??'Urmează traseul'}</strong></div></div>
      </div>
      <div className="tracker-hardkeys"><button aria-label="Reia previzualizarea de la început" disabled={!frame||inMission} onClick={()=>{setProgress(0);setPlaying(false);}}><Icon name="reset" size={19}/><span>RESET</span></button><button className="tracker-mainkey" disabled={!frame||inMission} onClick={()=>setPlaying(!playing)}><Icon name={playing?'pause':'play'} size={21}/><span>{playing?'PAUZĂ':'PREVIEW'}</span></button><button aria-label="Avansează 100 metri în previzualizare" disabled={!frame||inMission} onClick={()=>step(100)}><Icon name="chevron" size={22}/><span>PAS</span></button></div>
      <div className="tracker-bottommark"><span>JEZERO / SURFACE NAVIGATION</span><i/><i/><i/></div>
    </section>
    <aside className="tracker-description"><span className="eyebrow">Perspectiva astronautului</span><h2>Traseul, la nivelul privirii.</h2><p>Camera rămâne aproape de sol și privește înainte pe traseul ales. Linia portocalie urmărește relieful în fața ta.</p><div className="tracker-route-summary"><span>{inMission?'Traseu din simularea live':local?local.kind==='short'?'Varianta aleasă: distanță minimă':'Varianta aleasă: pantă ponderată':route?'Planul misiunii':'Selectează o destinație în Misiune'}</span><strong>{destination}</strong></div>
      {!inMission&&frame&&<label className="tracker-progress">Poziție în previzualizare <strong>{number(progress*100)}%</strong><input type="range" min="0" max="1" step=".001" value={progress} onChange={e=>{setProgress(Number(e.target.value));setPlaying(false);}}/><span>{number(frame.distance*site.cell_size_m)} m parcurși / {number(frame.total*site.cell_size_m)} m</span></label>}
      <p className="small muted">{inMission?'Camera urmărește poziția simulată a astronautului.':'Previzualizarea mută doar camera; nu consumă oxigen și nu pornește misiunea.'}</p><p className="small muted">Relief USGS cu exagerare verticală de afișare 6×. Carcasa este un concept vizual de echipament de teren.</p>
    </aside></div>}
  </div>;
}
