import {useMemo,useState} from 'react';
import Icon from '../Icon';
import {number} from '../../utils';
// Elevation along the trip, coloured by how steep the walk is, with the grade drawn underneath.
// The limit is the walking slope limit of the mission planner (20°).
const LIMIT=20,W=1000,X0=58,X1=986,TOP=16,BASE=150,MID=205,HALF=34;
const tone=slope=>{const s=Math.abs(slope);return s>LIMIT?'steep':s>=10?'moderate':'gentle';};
const labels={gentle:'Gentle',moderate:'Moderate',steep:'Steep'};
export default function TripProfile({profile=[],stops=[],label,busy,onHover}){
  const [index,setIndex]=useState(null);
  const chart=useMemo(()=>{
    if(profile.length<2)return null;
    const total=profile.at(-1).distance_m;let min=Infinity,max=-Infinity,ascent=0,descent=0,steepest=0,weighted=0,steepRun=0;
    profile.forEach((p,i)=>{min=Math.min(min,p.elevation_m);max=Math.max(max,p.elevation_m);steepest=Math.max(steepest,Math.abs(p.slope_deg));if(i){const d=p.elevation_m-profile[i-1].elevation_m,run=p.distance_m-profile[i-1].distance_m;if(d>0)ascent+=d;else descent-=d;weighted+=Math.abs(p.slope_deg)*run;if(Math.abs(p.slope_deg)>LIMIT)steepRun+=run;}});
    const span=Math.max(1,max-min),x=p=>X0+p.distance_m/total*(X1-X0),y=p=>BASE-(p.elevation_m-min)/span*(BASE-TOP),range=Math.max(25,Math.ceil(steepest/5)*5);
    // One path per steepness class, so the line changes colour exactly where the walk gets steeper.
    const lines={gentle:'',moderate:'',steep:''};
    for(let i=1;i<profile.length;i++)lines[tone(profile[i].slope_deg)]+=`M${x(profile[i-1]).toFixed(1)} ${y(profile[i-1]).toFixed(1)}L${x(profile[i]).toFixed(1)} ${y(profile[i]).toFixed(1)}`;
    const area=`M${X0} ${BASE+8}`+profile.map(p=>`L${x(p).toFixed(1)} ${y(p).toFixed(1)}`).join('')+`L${X1} ${BASE+8}Z`;
    const bar=(X1-X0)/(profile.length-1),bars=profile.map((p,i)=>{const h=Math.min(HALF,Math.abs(p.slope_deg)/range*HALF);return {x:x(p)-bar/2,w:Math.max(.6,bar-.3),y:p.slope_deg>=0?MID-h:MID,h,tone:tone(p.slope_deg),i};});
    const marks=stops.map((s,n)=>{let best=0,dist=Infinity;profile.forEach((p,i)=>{const d=Math.hypot(p.row-s.row,p.col-s.col);if(d<dist){dist=d;best=i;}});return dist<=3?{n:n+1,name:s.name.split(',')[0],x:x(profile[best]),y:y(profile[best])}:null;}).filter(Boolean);
    return {total,min,max,ascent,descent,steepest,average:weighted/total,steepShare:steepRun/total*100,x,y,lines,area,bars,marks,limitY:LIMIT/range*HALF,key:profile.length+':'+total.toFixed(0)+':'+min.toFixed(1)+':'+max.toFixed(1)};
  },[profile,stops]);
  const current=chart&&index!==null?profile[Math.min(index,profile.length-1)]:null;
  function choose(i){setIndex(i);onHover?.(i===null?null:profile[i]);}
  function pointer(e){const rect=e.currentTarget.getBoundingClientRect(),px=(e.clientX-rect.left)/rect.width*W;choose(Math.max(0,Math.min(profile.length-1,Math.round((px-X0)/(X1-X0)*(profile.length-1)))));}
  function keys(e){if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const step=Math.max(1,Math.round(profile.length/60));choose(e.key==='Home'?0:e.key==='End'?profile.length-1:Math.max(0,Math.min(profile.length-1,(index??0)+(e.key==='ArrowRight'?step:-step))));}
  const stats=chart?[['Distance',number(chart.total/1000,2),'km'],['Ascent',number(chart.ascent),'m'],['Descent',number(chart.descent),'m'],['Elevation',`${number(chart.min)} to ${number(chart.max)}`,'m'],['Average slope',number(chart.average,1),'°'],['Steepest',number(chart.steepest,1),'°',tone(chart.steepest)],[`Over ${LIMIT}°`,number(chart.steepShare,1),'%',chart.steepShare>0?'steep':'gentle']]:[];
  return <section className={`trip-profile ${busy?'is-busy':''}`} aria-label="Trip elevation and slope profile">
    <header className="tp-head"><div><span className="eyebrow">Terrain along the walk</span><h3><Icon name="activity" size={16}/>Elevation & slope</h3></div><span className="tp-label">{busy?'Updating…':label??'No trip yet'}</span></header>
    {chart?<>
      <dl className="tp-stats" key={chart.key}>{stats.map(([name,value,unit,flag],i)=><div key={name} className={flag?`tp-${flag}`:''} style={{'--i':i}}><dt>{name}</dt><dd>{value}<small>{unit}</small></dd></div>)}</dl>
      <div className="tp-chart">
        <svg viewBox={`0 0 ${W} 262`} role="img" tabIndex="0" aria-label={`Elevation and walking slope along ${number(chart.total/1000,2)} kilometres. Use the left and right arrows to inspect the trip.`} onPointerMove={pointer} onPointerLeave={()=>choose(null)} onKeyDown={keys} onBlur={()=>choose(null)}>
          <defs><linearGradient id="tp-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e97845" stopOpacity=".34"/><stop offset="1" stopColor="#e97845" stopOpacity="0"/></linearGradient><clipPath id="tp-clip"><rect key={chart.key} className="tp-reveal" x={X0-6} y="0" width={X1-X0+12} height="262"/></clipPath></defs>
          <path className="tp-grid" d={`M${X0} ${TOP}H${X1}M${X0} ${(TOP+BASE)/2}H${X1}M${X0} ${BASE}H${X1}M${X0} ${MID}H${X1}`}/>
          <path className="tp-limit" d={`M${X0} ${MID-chart.limitY}H${X1}M${X0} ${MID+chart.limitY}H${X1}`}/>
          <text x={X0-8} y={TOP+4} textAnchor="end">{number(chart.max)} m</text><text x={X0-8} y={BASE+3} textAnchor="end">{number(chart.min)} m</text>
          <text x={X0-8} y={MID-chart.limitY+3} textAnchor="end">+{LIMIT}°</text><text x={X0-8} y={MID+chart.limitY+3} textAnchor="end">−{LIMIT}°</text>
          <text className="tp-axis-title" x={X0} y={MID-HALF-5}>Slope: uphill above the line, downhill below</text>
          {[0,.25,.5,.75,1].map(f=><text key={f} x={X0+(X1-X0)*f} y="258" textAnchor={f===0?'start':f===1?'end':'middle'}>{f===0?'Start':number(chart.total*f/1000,2)+' km'}</text>)}
          <g clipPath="url(#tp-clip)">
            <path d={chart.area} fill="url(#tp-fill)"/>
            {chart.bars.map(b=><rect key={b.i} className={`tp-bar tp-${b.tone}`} x={b.x} y={b.y} width={b.w} height={b.h}/>)}
            {Object.entries(chart.lines).map(([name,d])=>d&&<path key={name} className={`tp-line tp-${name}`} d={d}/>)}
            {chart.marks.map(mark=><g key={mark.n} className="tp-mark"><path d={`M${mark.x} ${mark.y}V${BASE+8}`}/><circle cx={mark.x} cy={mark.y} r="9"/><text x={mark.x} y={mark.y+3.5} textAnchor="middle">{mark.n}</text><title>{mark.name}</title></g>)}
          </g>
          {current&&<g className="tp-cursor"><path d={`M${chart.x(current)} ${TOP-6}V${MID+HALF}`}/><circle cx={chart.x(current)} cy={chart.y(current)} r="5"/></g>}
        </svg>
        {current&&<div className={`tp-tip tp-${tone(current.slope_deg)}`} style={{left:`${chart.x(current)/W*100}%`}} data-side={chart.x(current)>W*.72?'left':'right'} aria-live="polite"><strong>{number(current.distance_m/1000,2)} km</strong><span>{number(current.elevation_m,1)} m elevation</span><span><i/>{current.slope_deg>=0?'Uphill':'Downhill'} {number(Math.abs(current.slope_deg),1)}° · {labels[tone(current.slope_deg)]}</span></div>}
      </div>
      <footer className="tp-foot"><div className="tp-legend"><span><i className="tp-gentle"/>Gentle, under 10°</span><span><i className="tp-moderate"/>Moderate, 10 to {LIMIT}°</span><span><i className="tp-steep"/>Steep, over {LIMIT}° (walking limit)</span></div><span>Hover the chart to see the point on the map · source elevations, no vertical exaggeration</span></footer>
    </>:<div className="tp-empty"><Icon name="activity" size={22}/><p>Add a stop to your trip and the elevation and slope of the walk appear here.</p></div>}
  </section>;
}
