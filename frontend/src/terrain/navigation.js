// Échantillonnage par distance du parcours choisi, en cellules de la grille.
const routeLengths = new WeakMap();
// Paths are immutable API/worker results. Reuse their distance index across map,
// tracker and watch frames instead of rebuilding it during every animation tick.
export function advancePreview(progress, meters, totalCells, cellSize) {
  if (![progress,meters,totalCells,cellSize].every(Number.isFinite)||totalCells<=0||cellSize<=0)return progress;
  return Math.max(0,Math.min(1,progress+meters/(totalCells*cellSize)));
}
export function routeFrame(path, fraction = 0, position = null, lookAheadCells = 3) {
  if (!Array.isArray(path) || path.length < 2) return null;
  let lengths = routeLengths.get(path);
  if(!lengths){lengths=[0];for (let i=1;i<path.length;i++) lengths.push(lengths[i-1]+Math.hypot(path[i][0]-path[i-1][0],path[i][1]-path[i-1][1]));routeLengths.set(path,lengths);}
  const total=lengths.at(-1);
  if (!total) return null;
  let distance=Math.max(0,Math.min(1,fraction))*total;
  if(position) {
    let best=Infinity;const fits=[];
    for(let i=1;i<path.length;i++) { const a=path[i-1],b=path[i],dr=b[0]-a[0],dc=b[1]-a[1],d=dr*dr+dc*dc;if(!d)continue;const t=Math.max(0,Math.min(1,((position.row-a[0])*dr+(position.col-a[1])*dc)/d));const error=(position.row-a[0]-dr*t)**2+(position.col-a[1]-dc*t)**2;fits.push([error,lengths[i-1]+Math.sqrt(d)*t]);best=Math.min(best,error); }
    // On an out-and-back route the way home crosses the same cells as the way out, and the animated live
    // position trails the start of the remaining path by up to one tick of walking (~2-4 cells). Take the
    // first match along the path (within 4 cells of the best), so the view looks ahead, never back home.
    const first=fits.find(([error])=>error<=best+16);if(first)distance=first[1];
  }
  function sample(d) { let i=1;while(i<lengths.length-1&&lengths[i]<d)i++;const f=(d-lengths[i-1])/Math.max(1e-9,lengths[i]-lengths[i-1]);return {row:path[i-1][0]+(path[i][0]-path[i-1][0])*f,col:path[i-1][1]+(path[i][1]-path[i-1][1])*f}; }
  const eye=sample(distance),ahead=sample(Math.min(total,distance+lookAheadCells));
  // Au point d'arrivée, conserve l'orientation du dernier segment.
  if(distance>=total-.001){const behind=sample(Math.max(0,total-lookAheadCells));ahead.row=eye.row+(eye.row-behind.row);ahead.col=eye.col+(eye.col-behind.col);}
  return {eye,ahead,distance,total,remaining:Math.max(0,total-distance),heading:(Math.atan2(ahead.col-eye.col,-(ahead.row-eye.row))*180/Math.PI+360)%360};
}

// Grid rows increase southward. Bearings are degrees clockwise from grid north.
export function bearingTo(from,to) {
  if(![from?.row,from?.col,to?.row,to?.col].every(Number.isFinite))return null;
  const dr=to.row-from.row,dc=to.col-from.col;
  if(Math.hypot(dr,dc)<1e-9)return null;
  return (Math.atan2(dc,-dr)*180/Math.PI+360)%360;
}
export function distanceTo(from,to,cellSize) {
  if(![from?.row,from?.col,to?.row,to?.col,cellSize].every(Number.isFinite)||cellSize<=0)return null;
  return Math.hypot(to.row-from.row,to.col-from.col)*cellSize;
}
