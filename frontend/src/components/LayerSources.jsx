import Icon from './Icon';

const sourceLabels={nasa:'NASA data',synthetic:'Synthetic',assumption:'Assumption',source:'Source', 'to verify':'To verify'};
export default function LayerSources({site}) {
  const layers=Array.isArray(site.layers)?site.layers:[];
  const synthetic=site.site_id==='synthetic';
  return <details className="planning-sources">
    <summary><Icon name="layers" size={16}/><span>Planning data sources</span><small>{layers.length} layers</small></summary>
    <p className="sources-context">Metadata from the active planning site. The 3D presentation uses its separately packaged USGS CTX relief.</p>
    {layers.length?layers.map(layer=>{
      const source=layer.source??(synthetic?'synthetic':null);
      const fields=[['Mission',layer.mission],['Instrument',layer.instrument],['Data type',layer.data_type],['Analog of',layer.analog_of],['Product',layer.product_id]].filter(([,value])=>typeof value==='string'&&value);
      return <article className="layer-source" key={layer.id}>
        <header><h4>{layer.label??layer.id}<small>{layer.unit?` / ${layer.unit}`:''}</small></h4><span className={`provenance-badge ${['assumption','synthetic','to verify'].includes(source)?'provisional':''}`}>{sourceLabels[source]??source??'Not supplied'}</span></header>
        {fields.length?<dl>{fields.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>:<p>{synthetic?'Illustrative synthetic layer; instrument metadata not supplied.':'Mission and instrument metadata not supplied.'}</p>}
      </article>;
    }):<p>No layer metadata supplied by the planning service.</p>}
  </details>;
}
