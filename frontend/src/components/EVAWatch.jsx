import { useEffect, useState } from 'react';
import { bearingTo, distanceTo, routeFrame } from '../terrain/navigation';
import { decisions, number } from '../utils';
import Icon from './Icon';
import '../watch.css';

function CompassDial({kind,bearing,arrived,unavailable,trace=[]}) {
  const available=Number.isFinite(bearing)&&!unavailable&&!arrived;
  return <div className={`wrist-compass ${kind}`}>
    <svg viewBox="0 0 150 150" role="img" aria-label={`${kind==='home'?'Habitat':'Route'} compass, ${arrived?'arrived':available?`${number(bearing)} degrees from north`:'direction unavailable'}`}>
      <circle className="dial-ring" cx="75" cy="75" r="63"/>
      {Array.from({length:24},(_,i)=><path key={i} className={`dial-tick ${i%6===0?'major':''}`} d={`M75 ${i%6===0?17:15}V${i%6===0?24:19}`} transform={`rotate(${i*15} 75 75)`}/>)}
      <text x="75" y="36" className="dial-north">N</text><text x="119" y="78">E</text><text x="75" y="122">S</text><text x="31" y="78">W</text>
      {trace.length>1&&<polyline className="dial-route" points={trace.map(p=>p.join(',')).join(' ')}/>}
      {available?<g transform={`rotate(${bearing} 75 75)`}><path className="dial-needle-tail" d="M75 105L69 76H81Z"/><path className="dial-needle" d="M75 42L67 79L75 73L83 79Z"/></g>:<text className="dial-empty" x="75" y="78">{arrived?'✓':'—'}</text>}
      <circle cx="75" cy="75" r="3" className="dial-hub"/>
    </svg>
    <span>{kind==='home'?'HABITAT':'MISSION ROUTE'}</span><strong>{arrived?'Arrived':available?`${number(bearing)}°`:'—'}</strong>
  </div>;
}

export default function EVAWatch({equipment,site,route,live,position,path,frame,progress,setProgress,playing,setPlaying,embedded=false}) {
  const active=!!live.tick&&live.state!=='idle';
  const [clock,setClock]=useState(()=>new Date());
  useEffect(()=>{const timer=setInterval(()=>setClock(new Date()),1000);return()=>clearInterval(timer);},[]);
  const origin=active?position??live.tick.astronaut:frame?.eye;
  const activePath=active?live.tick.remaining_path:path;
  const guidance=active?routeFrame(activePath,0,origin):frame;
  const baseDistance=distanceTo(origin,site.habitat,site.cell_size_m);
  const baseBearing=bearingTo(origin,site.habitat);
  const atBase=baseDistance!==null&&baseDistance<1;
  const endpoint=activePath?.length===1?{row:activePath[0][0],col:activePath[0][1]}:null;
  const endpointDistance=distanceTo(origin,endpoint,site.cell_size_m);
  const remaining=guidance?guidance.remaining*site.cell_size_m:endpointDistance!==null&&endpointDistance<1?0:null;
  const atGoal=remaining!==null&&remaining<1;
  const routeBearing=guidance&&!atGoal?bearingTo(origin,guidance.ahead):null;
  const offline=active&&['offline','reconnecting','invalid'].includes(live.status);
  const waiting=active&&live.decision?.decision==='WAIT';
  const trace=guidance&&origin?[[75,75],[75+(guidance.ahead.col-origin.col)*6,75+(guidance.ahead.row-origin.row)*6]]:[];
  const time=clock.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
  const decision=live.decision?.decision;
  return <div className={`eva-watch-layout ${embedded?'embedded-watch':''}`}>
    <div className="wrist-assembly">
      <div className="watch-strap strap-top" aria-hidden="true"><i/><i/><i/></div>
      <section className="eva-watch" aria-label="EVA watch with habitat and route compasses">
        <div className="watch-bezel-text">MARSWALK <span>EVA / NAVIGATION</span></div><i className="watch-case-screw one"/><i className="watch-case-screw two"/>
        <div className="watch-crown" aria-hidden="true"/>
        <div className="eva-watch-screen">
          <div className="wrist-status"><span className={offline?'link-lost':''}><i/>{offline?'LINK LOST':active?'MISSION LIVE':'ROUTE PREVIEW'}</span><time>{time}<small> LOCAL</small></time></div>
          <div className="wrist-heading"><span>{waiting?'Hold position':atGoal?'Route complete':decision==='RETURN'?'Return to habitat':'Surface navigation'}</span><Icon name={waiting?'pause':'compass'} size={17}/></div>
          <div className="dual-compasses"><CompassDial kind="home" bearing={baseBearing} arrived={atBase} unavailable={offline}/><CompassDial kind="route" bearing={routeBearing} arrived={atGoal} unavailable={offline||waiting} trace={trace}/></div>
          <div className="wrist-distances"><div><span>Habitat · direct</span><strong>{number(baseDistance===null?null:baseDistance/1000,2)}<small> km</small></strong></div><div><span>Route remaining</span><strong>{number(remaining===null?null:remaining/1000,2)}<small> km</small></strong></div></div>
          <div className="wrist-route-instruction"><Icon name={offline?'alert':waiting?'pause':'arrow'} size={18}/><span>{offline?'Navigation held · reconnect telemetry':waiting?'Wait for the next mission decision':atGoal?'You reached the end of this route':Number.isFinite(routeBearing)?`Follow route · ${number(routeBearing)}° N`:'Select a route to begin'}</span></div>
          <div className="wrist-vitals"><span>O₂ <b>{number(equipment?equipment.readings.o2_pct.value:live.tick?.sensors?.o2_pct,1)}%</b></span><span>t+{number(live.tick?.t_min??0)} min</span><span>NORTH UP</span></div>
        </div>
        <div className="watch-bezel-bottom"><span>HABITAT</span><i/><span>ROUTE</span></div>
      </section>
      <div className="watch-strap strap-bottom" aria-hidden="true"><i/><i/><i/><i/></div>
    </div>
    {!embedded&&<aside className="watch-explanation"><span className="eyebrow">Two bearings. One glance.</span><h2>Keep home in sight.<br/>Stay on your route.</h2><div className="watch-key home"><Icon name="target" size={19}/><div><h3>Habitat compass</h3><p>Always points toward the base from your current grid position. Distance is measured in a straight line.</p></div></div><div className="watch-key route"><Icon name="compass" size={19}/><div><h3>Mission tracker</h3><p>Follows the next segment of the selected route and updates as the astronaut advances or the copilot reroutes.</p></div></div>
      {!active&&frame&&<div className="watch-preview-controls"><label htmlFor="watch-position">Preview position <b>{number(progress*100)}%</b></label><input id="watch-position" type="range" min="0" max="1" step=".001" value={progress} onChange={e=>{setProgress(Number(e.target.value));setPlaying(false);}}/><div><button className="button secondary" onClick={()=>{setProgress(0);setPlaying(false);}}><Icon name="reset" size={15}/>Reset</button><button className="button primary" onClick={()=>setPlaying(!playing)}><Icon name={playing?'pause':'play'} size={15}/>{playing?'Pause preview':'Play preview'}</button></div></div>}
      <p className="watch-data-note">{active?`${decisions[decision]??'Following the mission route'}. Bearings use the simulated live position.`:'Preview follows the selected route. Start an EVA for live mission tracking.'}</p><p className="watch-data-note">Both dials keep grid north at the top. Suit orientation is not supplied. The habitat arrow is a bearing, not a validated return path.</p>
    </aside>}
  </div>;
}
