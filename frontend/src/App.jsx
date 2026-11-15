import {lazy} from 'react';
import {Navigate,Route,Routes} from 'react-router-dom';
import {MissionProvider} from './mission/MissionContext';
import AppLayout from './layout/AppLayout';
import PlanningPage from './pages/PlanningPage';
// Simulation and Sensors load on first visit; Planning is the landing page and ships in the main bundle.
const SimulationPage=lazy(()=>import('./pages/SimulationPage'));
const SensorsPage=lazy(()=>import('./pages/SensorsPage'));
export default function App(){
  return <MissionProvider><Routes><Route element={<AppLayout/>}>
    <Route index element={<Navigate to="/planning" replace/>}/>
    <Route path="planning" element={<PlanningPage/>}/>
    <Route path="simulation" element={<SimulationPage/>}/>
    <Route path="sensors" element={<SensorsPage/>}/>
    <Route path="*" element={<Navigate to="/planning" replace/>}/>
  </Route></Routes></MissionProvider>;
}
