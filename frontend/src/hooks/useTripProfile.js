import {useEffect,useState} from 'react';
import {loadTerrain} from '../api/client';
import {terrainProfile} from '../terrain/explorer';
// Elevation samples along a path, with the grade the astronaut actually walks between samples.
// Source elevations only (no display exaggeration). `slope_deg` is signed: positive = uphill.
export function useTripProfile(path){
  const [profile,setProfile]=useState([]),key=path?path.length+':'+path[0]+':'+path[Math.floor(path.length/2)]+':'+path.at(-1):'';
  useEffect(()=>{
    if(!path||path.length<2){setProfile([]);return;}
    let active=true;
    loadTerrain().then(({grid})=>{
      if(!active)return;
      const samples=terrainProfile(grid,path,600);
      setProfile(samples.map((p,i)=>{const a=samples[Math.max(0,i-1)],b=samples[Math.min(samples.length-1,i+1)],run=b.distance_m-a.distance_m;return {...p,slope_deg:run>0?Math.atan2(b.elevation_m-a.elevation_m,run)*180/Math.PI:0};}));
    }).catch(()=>{if(active)setProfile([]);});
    return()=>{active=false;};
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[key]);
  return profile;
}
