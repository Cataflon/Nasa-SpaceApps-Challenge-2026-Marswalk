// Adaptare a A* din macheta furnizată: 8 vecini și cost după pantă.
// Folosește exclusiv altitudinile USGS originale, fără exagerarea verticală.
let grid;
class Heap {
  a = [];
  push(node) { const a=this.a; a.push(node); let i=a.length-1; while(i>0){const p=(i-1)>>1;if(a[p][0]<=node[0])break;a[i]=a[p];i=p;}a[i]=node; }
  pop() { const a=this.a,first=a[0],last=a.pop();if(a.length){let i=0;while(i*2+1<a.length){let c=i*2+1;if(c+1<a.length&&a[c+1][0]<a[c][0])c++;if(a[c][0]>=last[0])break;a[i]=a[c];i=c;}a[i]=last;}return first; }
}
function plan(start, goal, safe) {
  const {rows,cols,elevation:z,cell_size_m:cell}=grid,N=rows*cols;
  const s=start.row*cols+start.col,t=goal.row*cols+goal.col;
  const g=new Float64Array(N).fill(Infinity),came=new Int32Array(N).fill(-1),closed=new Uint8Array(N),heap=new Heap();
  g[s]=0;heap.push([0,s]);
  const slope=(a,b,d)=>Math.atan(Math.abs(z[b]-z[a])/d)*180/Math.PI;
  while(heap.a.length){const [,i]=heap.pop();if(closed[i])continue;closed[i]=1;if(i===t)break;const r=Math.floor(i/cols),c=i%cols;
    for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){if(!dr&&!dc)continue;const nr=r+dr,nc=c+dc;if(nr<0||nc<0||nr>=rows||nc>=cols)continue;const j=nr*cols+nc;if(closed[j])continue;const d=Math.hypot(dr,dc)*cell,sl=slope(i,j,d);if(sl>25)continue;
      if(dr&&dc&&(slope(i,r*cols+nc,cell)>25||slope(i,nr*cols+c,cell)>25))continue;
      const next=g[i]+d*(safe?1+(sl/15)**2:1);if(next<g[j]){g[j]=next;came[j]=i;heap.push([next+Math.hypot(nr-goal.row,nc-goal.col)*cell,j]);}
    }
  }
  if(s!==t&&came[t]<0)return null;
  const path=[];for(let i=t;i!==-1;i=came[i])path.push([Math.floor(i/cols),i%cols]);path.reverse();
  let distance=0,ascent=0,maxSlope=0;for(let k=1;k<path.length;k++){const a=path[k-1],b=path[k],i=a[0]*cols+a[1],j=b[0]*cols+b[1],d=Math.hypot(b[0]-a[0],b[1]-a[1])*cell;distance+=d;ascent+=Math.max(0,z[j]-z[i]);maxSlope=Math.max(maxSlope,slope(i,j,d));}
  return {path,distance,ascent,maxSlope};
}
self.onmessage=({data})=>{if(data.type==='grid'){grid=data.grid;return;}try{if(!grid)throw Error('Relieful nu este încă disponibil.');const {start,goal,id}=data;for(const p of [start,goal])if(!Number.isInteger(p.row)||!Number.isInteger(p.col)||p.row<0||p.col<0||p.row>=grid.rows||p.col>=grid.cols)throw Error('Punct în afara grilei.');self.postMessage({id,safe:plan(start,goal,true),short:plan(start,goal,false)});}catch(error){self.postMessage({id:data.id,error:error.message});}};
