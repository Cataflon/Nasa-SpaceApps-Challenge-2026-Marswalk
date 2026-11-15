import Icon from '../Icon';
import EquipmentSource from '../sensors/EquipmentSource';
import {modules,equipmentReading,stateNames} from '../../sensors/equipment';
import {number} from '../../utils';
export default function SensorSummary({live,feed,onDetails}){
  return <section className="flight-sensors"><div className="workflow-section-heading"><div><span className="eyebrow">Current telemetry</span><h2>Astronaut & environment</h2></div><div className="summary-source-actions">{feed&&<EquipmentSource feed={feed}/>}<button className="button secondary" onClick={onDetails}>Sensor details<Icon name="chevron" size={14}/></button></div></div><div className="sensor-summary-grid">{modules.map(m=>{const r=feed?.readings[m.key]??equipmentReading(m,live.tick,live.status);return <div className={`sensor-summary-card state-${r.state}`} key={m.key}><span>{m.name}</span><strong>{number(r.value,m.key==='dust_tau'?2:1)}<small>{m.unit}</small></strong><p><i/>{stateNames[r.state]}</p></div>;})}</div><p className="sensor-summary-note">{feed?.demo?'Equipment simulator - shared simulated diagnostics':live.receivedAt?`Last received ${new Date(live.receivedAt).toLocaleTimeString()}`:'Waiting for an active EVA'} · environmental channels describe conditions outside the suit.</p></section>;
}
