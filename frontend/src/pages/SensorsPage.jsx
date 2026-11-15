import {useMissionContext} from '../mission/MissionContext';
import Sensors from '../components/sensors/Sensors';
// Sensors: every suit and environment channel in detail, fed by the same live mission.
export default function SensorsPage(){
  const {live,equipment}=useMissionContext();
  return <Sensors live={live} feed={equipment}/>;
}
