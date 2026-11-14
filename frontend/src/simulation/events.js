// Editable fields supported by the current live engine. Units are API units.
export const eventSpecs={
  local_storm:{label:'Local storm',spatial:true,defaults:{axis_a:15000,axis_b:2500,angle_deg:90,intensity:.7,velocity_row:0,velocity_col:15}},
  regional_storm:{label:'Regional storm',spatial:true,defaults:{axis_a:30000,axis_b:30000,angle_deg:0,intensity:.9,velocity_row:0,velocity_col:0}},
  dust_devil:{label:'Dust devil',spatial:true,defaults:{axis_a:65,axis_b:65,angle_deg:0,intensity:.9,velocity_row:0,velocity_col:4}},
  marsquake:{label:'Marsquake zone',spatial:true,defaults:{axis_a:300,axis_b:300,angle_deg:0,intensity:1,velocity_row:0,velocity_col:0}},
  solar_particle_event:{label:'Solar particle event',fields:[['dose_rate_multiplier','Dose multiplier',1,100,.1],['duration_min','Duration (min)',1,10080,1]],defaults:{dose_rate_multiplier:2.5,duration_min:240}},
  suit_leak:{label:'Suit leak',fields:[['leak_pct_per_min','Extra O₂ loss (% / min)',.001,10,.001]],defaults:{leak_pct_per_min:.15}},
  fatigue:{label:'Fatigue',fields:[['speed_factor','Speed factor',.01,1,.01]],defaults:{speed_factor:.8}}
};
export const spatialFields=[['axis_a','Radius / semi-axis A (m)',1,100000,1],['axis_b','Radius / semi-axis B (m)',1,100000,1],['angle_deg','Ellipse angle (°)',0,360,1],['intensity','Intensity (0–1)',0,1,.01],['velocity_row','South velocity (m/s)',-100,100,.1],['velocity_col','East velocity (m/s)',-100,100,.1]];
export function eventPayload(kind,values,site){
  const spec=eventSpecs[kind];if(!spec)throw Error('Unknown event type.');
  for(const [key,label,min,max] of spec.spatial?spatialFields:spec.fields){const n=Number(values[key]);if(!Number.isFinite(n)||n<min||n>max)throw Error(`${label} must be between ${min} and ${max}.`);}
  if(spec.spatial){const row=Number(values.row),col=Number(values.col);if(!Number.isInteger(row)||!Number.isInteger(col)||row<0||col<0||row>=site.shape[0]||col>=site.shape[1])throw Error('Event center must be inside the site grid.');return {center:{row,col},axes_m:[Number(values.axis_a),Number(values.axis_b)],angle_deg:Number(values.angle_deg),intensity:Number(values.intensity),velocity_ms:[Number(values.velocity_row),Number(values.velocity_col)]};}
  return Object.fromEntries(spec.fields.map(([key])=>[key,Number(values[key])]));
}
