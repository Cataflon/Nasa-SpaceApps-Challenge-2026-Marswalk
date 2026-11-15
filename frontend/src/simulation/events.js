// Events are placed on the map; only the optional fine-tuning values are typed. Units are API units.
// place: 'direction' = center -> radius -> heading, 'area' = center -> radius, 'tap' = one click anywhere (site-wide), 'astronaut' = click the astronaut.
export const eventSpecs={
  local_storm:{icon:'wind',group:'weather',label:'Local storm',place:'direction',color:0xe25d5d,help:'Pick where it starts, size it, then aim it.',fields:[['speed_ms','Speed (m/s)',0,100,.5],['intensity','Intensity (0–1)',0,1,.05]],defaults:{speed_ms:15,intensity:.7}},
  regional_storm:{icon:'cloud',group:'weather',label:'Regional storm',place:'direction',color:0xe25d5d,help:'Pick where it starts, size it, then aim it.',fields:[['speed_ms','Speed (m/s)',0,100,.5],['intensity','Intensity (0–1)',0,1,.05]],defaults:{speed_ms:10,intensity:.9}},
  dust_devil:{icon:'tornado',group:'weather',label:'Dust devil',place:'direction',color:0xe25d5d,help:'Pick where it starts, size it, then aim it. Zoom in: dust devils are small.',fields:[['speed_ms','Speed (m/s)',0,100,.5],['intensity','Intensity (0–1)',0,1,.05]],defaults:{speed_ms:4,intensity:.9}},
  marsquake:{icon:'activity',group:'ground',label:'Marsquake zone',place:'area',color:0xe25d5d,help:'Pick the epicenter, then size the affected zone.',fields:[['intensity','Intensity (0–1)',0,1,.05]],defaults:{intensity:1}},
  solar_particle_event:{icon:'sun',group:'radiation',label:'Solar particle event',place:'tap',color:0xffc24a,marker:true,help:'Click anywhere on the map: radiation rises across the whole site and the map glows until it ends.',fields:[['dose_rate_multiplier','Dose multiplier',1,100,.1],['duration_min','Duration (min)',1,10080,1]],defaults:{dose_rate_multiplier:2.5,duration_min:240}},
  suit_leak:{icon:'droplet',group:'suit',label:'Suit leak',place:'astronaut',help:'Click the astronaut on the map to start the leak.',fields:[['leak_pct_per_min','Extra O₂ loss (% / min)',.001,10,.001]],defaults:{leak_pct_per_min:.15}},
  fatigue:{icon:'battery',group:'suit',label:'Fatigue',place:'astronaut',help:'Click the astronaut on the map to slow them down.',fields:[['speed_factor','Speed factor',.01,1,.01]],defaults:{speed_factor:.8}}
};
// `placed` comes from the map: {center:{row,col}, radius_m, dir:[south,east] unit vector | null}.
export function eventPayload(kind,values,placed,site){
  const spec=eventSpecs[kind];if(!spec)throw Error('Unknown event type.');
  const v={};for(const [key,label,min,max] of spec.fields){const n=Number(values[key]);if(!Number.isFinite(n)||n<min||n>max)throw Error(`${label} must be between ${min} and ${max}.`);v[key]=n;}
  if(spec.place==='astronaut'||spec.marker)return v;
  const row=Math.round(placed?.center?.row),col=Math.round(placed?.center?.col),radius=Number(placed?.radius_m);
  if(!Number.isInteger(row)||!Number.isInteger(col)||row<0||col<0||row>=site.shape[0]||col>=site.shape[1])throw Error('Place the event inside the map.');
  if(!Number.isFinite(radius)||radius<1||radius>100000)throw Error('Radius must be between 1 m and 100 km.');
  const speed=v.speed_ms??0,dir=placed.dir??[0,0];
  return {center:{row,col},axes_m:[radius,radius],angle_deg:0,intensity:v.intensity,velocity_ms:[dir[0]*speed,dir[1]*speed]};
}
