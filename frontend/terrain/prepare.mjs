import { fromFile } from 'geotiff';
import fs from 'node:fs/promises';
const input = process.argv[2] || 'terrain/source/jezero-ctx-20m.tif';
const tiff = await fromFile(input);
try {
  const image = await tiff.getImage();
  const [x0,y0] = image.getOrigin(), [dx,dy] = image.getResolution();
  const keys = image.getGeoKeys();
  const width = image.getWidth(), height = image.getHeight();
  // Centrul se proiectează din lat/lon marțiene în proiecția equirectangulară a produsului.
  const radius = Number(keys.GeogSemiMajorAxisGeoKey || 3396190);
  const lon0 = Number(keys.ProjCenterLongGeoKey ?? keys.ProjNatOriginLongGeoKey ?? 0);
  const lat0 = Number(keys.ProjCenterLatGeoKey ?? keys.ProjNatOriginLatGeoKey ?? 0);
  const latTs = Number(keys.ProjStdParallel1GeoKey ?? 0);
  const lon = 77.45, lat = 18.44;
  const cx = radius * (lon-lon0) * Math.PI/180 * Math.cos(latTs*Math.PI/180);
  const cy = radius * (lat-lat0) * Math.PI/180;
  const col = Math.round((cx-x0)/dx), row = Math.round((cy-y0)/dy);
  const cols = Math.round(10000/Math.abs(dx)), rows = Math.round(10000/Math.abs(dy));
  const left = col-Math.floor(cols/2), top = row-Math.floor(rows/2);
  if(left<0 || top<0 || left+cols>width || top+rows>height) throw Error('Zona de 10 km nu este acoperită; verifică proiecția/centrul.');
  const raster = await image.readRasters({window:[left,top,left+cols,top+rows],interleave:true});
  const nodata = Number(image.getGDALNoData());
  const elevation = Array.from(raster, n => Number.isFinite(n) && n !== nodata && n > -10000 ? Math.round(n*100)/100 : null);
  if(elevation.some(n=>n===null)) throw Error('Decupajul conține NoData. Alege o zonă completă.');
  const result = { source:'USGS Mars 2020 CTX TRN DTM', sourceUrl:'https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif', center:{lat,lon}, rows, cols, cell_size_m:Math.abs(dx), elevation, referenceElevation:elevation.reduce((a,b)=>Math.min(a,b),Infinity), geoKeys:keys, origin:[x0+left*dx,y0+top*dy], resolution:[dx,dy], displayOnly:true };
  await fs.mkdir('public/terrain',{recursive:true}); await fs.writeFile('public/terrain/jezero.json', JSON.stringify(result));
  console.log({width,height,rows,cols,keys,min:result.referenceElevation,max:elevation.reduce((a,b)=>Math.max(a,b),-Infinity)});
} finally { await tiff.close(); }

