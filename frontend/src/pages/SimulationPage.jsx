import {useNavigate} from 'react-router-dom';
import {useMissionContext} from '../mission/MissionContext';
import SimulationWorkspace from '../components/simulation/SimulationWorkspace';
// Simulation: the live EVA on the map, the astronaut devices, the copilot and the event controls.
export default function SimulationPage(){
  const m=useMissionContext(),navigate=useNavigate();
  return <SimulationWorkspace equipment={m.equipment} site={m.site} mapSite={m.mapSite} route={m.route} live={m.live} offline={m.offline} transport={m.transport} selected={m.selected} onSelect={m.setSelected} onSensors={()=>navigate('/sensors')} onPlanning={()=>navigate('/planning')} mock={m.mock} onCopilotRoute={m.planner.setResult}/>;
}
