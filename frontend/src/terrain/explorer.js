// Source-space calculations. Display exaggeration never enters scientific metrics.
export function elevationAt(grid,row,col) {
  if(!grid||!Number.isFinite(row)||!Number.isFinite(col)||row<0||col<0||row>grid.rows-1||col>grid.cols-1)return null;
  const r=Math.min(Math.floor(row),grid.rows-2),c=Math.min(Math.floor(col),grid.cols-2),fr=row-r,fc=col-c,z=grid.elevation;
  const a=z[r*grid.cols+c],b=z[r*grid.cols+c+1],d=z[(r+1)*grid.cols+c],e=z[(r+1)*grid.cols+c+1];
  return fr+fc<=1?a+(b-a)*fc+(d-a)*fr:e+(d-e)*(1-fc)+(b-e)*(1-fr);
}
export function slopeAt(grid,row,col) {
  const r=Math.max(0,Math.min(grid.rows-1,Math.round(row))),c=Math.max(0,Math.min(grid.cols-1,Math.round(col)));
  const r0=Math.max(0,r-1),r1=Math.min(grid.rows-1,r+1),c0=Math.max(0,c-1),c1=Math.min(grid.cols-1,c+1),z=grid.elevation,cell=grid.cell_size_m;
  const dx=(z[r*grid.cols+c1]-z[r*grid.cols+c0])/((c1-c0)*cell),dy=(z[r1*grid.cols+c]-z[r0*grid.cols+c])/((r1-r0)*cell);
  return Math.atan(Math.hypot(dx,dy))*180/Math.PI;
}
export function terrainProfile(grid,path,limit=160) {
  if(!grid||!path?.length||path.some(p=>!Array.isArray(p)||!Number.isFinite(p[0])||!Number.isFinite(p[1])||elevationAt(grid,...p)===null))return [];
  const lengths=[0];for(let i=1;i<path.length;i++)lengths.push(lengths.at(-1)+Math.hypot(path[i][0]-path[i-1][0],path[i][1]-path[i-1][1])*grid.cell_size_m);
  const total=lengths.at(-1);if(!total)return [];
  const count=Math.max(2,Math.min(limit,Math.ceil(total/grid.cell_size_m)+1));let segment=1;
  return Array.from({length:count},(_,i)=>{const distance_m=total*i/(count-1);while(segment<path.length-1&&lengths[segment]<distance_m)segment++;
    const f=(distance_m-lengths[segment-1])/Math.max(1e-9,lengths[segment]-lengths[segment-1]),a=path[segment-1],b=path[segment],row=a[0]+(b[0]-a[0])*f,col=a[1]+(b[1]-a[1])*f;
    return {distance_m,elevation_m:elevationAt(grid,row,col),row,col};});
}
export function scaleDistance(pixelsPerMeter,maxPixels=100) {
  if(!Number.isFinite(pixelsPerMeter)||pixelsPerMeter<=0)return null;
  const raw=maxPixels/pixelsPerMeter,power=10**Math.floor(Math.log10(raw));
  const distance=[5,2,1].map(n=>n*power).find(n=>n<=raw)??power/2;
  return {meters:distance,pixels:distance*pixelsPerMeter};
}
