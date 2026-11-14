// Restore both GLTF material and its original vertex colors after analytic layers.
export function captureSurface(mesh){return {material:mesh.material,color:mesh.geometry.getAttribute('color')};}
export function restoreSurface(mesh,snapshot){
  mesh.material=snapshot.material;
  if(snapshot.color)mesh.geometry.setAttribute('color',snapshot.color);else mesh.geometry.deleteAttribute('color');
  for(const material of Array.isArray(mesh.material)?mesh.material:[mesh.material])material.needsUpdate=true;
}
