// Display metadata only: module locations and hardware images are conceptual.
export const modules = [
  {key:'o2_pct',name:'Oxygen reserve',code:'O₂',unit:'%',description:'Estimated oxygen remaining',location:'Life support / chest',side:'left',pin:[43,34],image:0,min:0,max:100,demo:68.5,accuracy:.5,action:'Compare with the life-support controller before using this estimate.'},
  {key:'dose_rate_usv_h',name:'Radiation dosimeter',code:'RAD',unit:'µSv/h',description:'External dose rate',location:'Upper torso / exposure',side:'right',pin:[64,31],image:1,min:0,demo:26.5,accuracy:1.2,action:'Cross-check exposure with the mission radiation feed.'},
  {key:'temp_c',name:'Temperature probe',code:'TMP',unit:'°C',description:'Ambient temperature, outside suit',location:'Forearm / environment',side:'left',pin:[28,49],image:2,min:-273.15,demo:-38,accuracy:.3,action:'Check the probe connection and compare with an independent ambient reading.'},
  {key:'pressure_pa',name:'Pressure transducer',code:'PRS',unit:'Pa',description:'Atmospheric pressure, not suit pressure',location:'Waist / environment',side:'right',pin:[58,49],image:3,min:0,demo:715,accuracy:2,action:'Verify the ambient sensor port. This channel cannot diagnose suit leakage.'},
  {key:'wind_ms',name:'Wind sensor',code:'WND',unit:'m/s',description:'Environmental wind speed',location:'Shoulder / illustrative attachment',side:'left',pin:[32,27],image:4,min:0,demo:11.2,accuracy:.4,action:'Cross-check with local weather telemetry; confirm the probe is unobstructed.'},
  {key:'dust_tau',name:'Optical dust monitor',code:'DST',unit:'τ',description:'Atmospheric dust opacity',location:'Lower leg / illustrative attachment',side:'right',pin:[63,72],image:5,min:0,demo:.9,accuracy:.04,action:'Inspect the optical window and compare with the environmental dust feed.'},
];
export const stateNames={ok:'Nominal',plausible:'Plausible',warning:'Check data',fault:'Sensor fault',waiting:'No reading'};

export function equipmentReading(module,tick,linkStatus,override) {
  const value=override?override.value:tick?.sensors?.[module.key];
  // Optional frontend adapter; existing telemetry does not yet supply this metadata.
  const health=override??tick?.sensor_health?.[module.key];
  const finite=Number.isFinite(value);
  const outside=finite&&((module.min!==undefined&&value<module.min)||(module.max!==undefined&&value>module.max));
  const disconnected=['offline','reconnecting','invalid'].includes(linkStatus);
  let state=finite?'plausible':'waiting';
  let reason=finite?'Value passes basic physical bounds. Hardware diagnostics are not supplied.':'No measurement has been received for this channel.';
  if(health?.state==='ok'&&finite){state='ok';reason=health.message||'Module reports normal operation.';}
  if(value!==null&&value!==undefined&&!finite){state='warning';reason='Measurement is not a finite number. It is excluded from the trend.';}
  if(outside){state='warning';reason='Value is outside basic physical bounds. Treat this reading as unverified.';}
  if(disconnected&&finite){state='warning';reason='Telemetry link interrupted. This is the last received value.';}
  if(health?.state==='warning'){state='warning';reason=health.message||'Module reports an invalid or uncertain measurement.';}
  if(health?.state==='fault'){state='fault';reason=health.message||'Module reports a hardware fault. Current reading is unavailable.';}
  const accuracy=health?.accuracy;
  return {value:state==='fault'?null:value,state,reason,valid:finite&&!outside&&state!=='fault',accuracy:Number.isFinite(accuracy?.value)&&accuracy.value>=0&&typeof accuracy.unit==='string'?accuracy:null,diagnostics:!!health?.state};
}

export function demoMeasurement(module,time,state='ok') {
  const amplitude=Math.max(.02,Math.abs(module.demo)*.006);
  return {value:Math.round((module.demo+Math.sin(time/3+module.image)*amplitude)*100)/100,state,accuracy:{value:module.accuracy,unit:module.unit},message:state==='fault'?'Simulated hardware fault: module self-test failed.':state==='warning'?'Simulated cross-check discrepancy. Reading requires verification.':'Simulated module self-test passed.'};
}
