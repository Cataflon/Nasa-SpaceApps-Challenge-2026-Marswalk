import { number } from '../utils';
export default function MissionMetrics({live}){
  const readings=[['O₂',live.tick?.sensors?.o2_pct,'%', 'Oxygen reserve'],['DAYLIGHT',live.tick?live.tick.budget?.sunset_min-live.tick.t_min:null,'min','Until sunset'],['DOSE',live.tick?.sensors?.dose_total_msv,'mSv','Accumulated exposure'],['WIND',live.tick?.sensors?.wind_ms,'m/s','Surface wind']];
  return <section className="instrument-strip" aria-label="Mission instruments">{readings.map(([label,value,unit,title])=><div className="instrument" key={label}><span>{label}</span><strong aria-label={title}>{number(value,2)}<small>{unit}</small></strong><i className={Number.isFinite(value)?'receiving':''}/></div>)}</section>;
}
