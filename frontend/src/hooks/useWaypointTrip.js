import {useEffect,useState} from 'react';
// Itinerarul ales pe hartă: id-urile opririlor și întoarcerea la habitat. Traseul îl calculează doar
// planificatorul din backend (useMissionEstimate → POST /api/route); frontendul nu mai are rutare proprie.
export function useWaypointTrip(site,points){
  const [ids,setIds]=useState([]),[returnHome,setReturnHome]=useState(true);
  const signature=points.map(p=>p.id).join('|');
  useEffect(()=>{setIds(previous=>previous.filter(id=>points.some(p=>p.id===id)));},[signature]);
  return {ids,setIds,returnHome,setReturnHome};
}
