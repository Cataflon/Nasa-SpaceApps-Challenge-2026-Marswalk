// Échantillonnage par distance du parcours choisi, en cellules de la grille.
export function routeFrame(path, fraction = 0, position = null, lookAheadCells = 3) {
  if (!Array.isArray(path) || path.length < 2) return null;
  const lengths = [0];
  for (let i=1;i<path.length;i++) lengths.push(lengths[i-1]+Math.hypot(path[i][0]-path[i-1][0],path[i][1]-path[i-1][1]));
  const total=lengths.at(-1);
  if (!total) return null;
  let distance=Math.max(0,Math.min(1,fraction))*total;
  if(position) {
    let best=Infinity;
    for(let i=1;i<path.length;i++) { const a=path[i-1],b=path[i],dr=b[0]-a[0],dc=b[1]-a[1],d=dr*dr+dc*dc;if(!d)continue;const t=Math.max(0,Math.min(1,((position.row-a[0])*dr+(position.col-a[1])*dc)/d));const error=(position.row-a[0]-dr*t)**2+(position.col-a[1]-dc*t)**2;if(error<best){best=error;distance=lengths[i-1]+Math.sqrt(d)*t;} }
  }
  function sample(d) { let i=1;while(i<lengths.length-1&&lengths[i]<d)i++;const f=(d-lengths[i-1])/Math.max(1e-9,lengths[i]-lengths[i-1]);return {row:path[i-1][0]+(path[i][0]-path[i-1][0])*f,col:path[i-1][1]+(path[i][1]-path[i-1][1])*f}; }
  const eye=sample(distance),ahead=sample(Math.min(total,distance+lookAheadCells));
  // Au point d'arrivée, conserve l'orientation du dernier segment.
  if(distance>=total-.001){const behind=sample(Math.max(0,total-lookAheadCells));ahead.row=eye.row+(eye.row-behind.row);ahead.col=eye.col+(eye.col-behind.col);}
  return {eye,ahead,distance,total,remaining:Math.max(0,total-distance),heading:(Math.atan2(ahead.col-eye.col,-(ahead.row-eye.row))*180/Math.PI+360)%360};
}
