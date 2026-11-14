export default function EquipmentSource({feed}){
  return <div className="equipment-source"><div className="segmented" aria-label="Shared sensor source"><button aria-pressed={!feed.demo} onClick={()=>feed.setDemo(false)}>Mission feed</button><button aria-pressed={feed.demo} onClick={()=>feed.setDemo(true)}>Equipment demo</button></div><span>{feed.demo?'Shared equipment demo · simulated data':feed.receivedAt?`Last received ${new Date(feed.receivedAt).toLocaleTimeString()}`:'Waiting for mission telemetry'}</span></div>;
}
