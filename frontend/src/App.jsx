import { useEffect, useState } from "react";
import { getSite, injectEvent, liveControl, planRoute, subscribeLive } from "./api/client.js";
import BudgetPanel from "./components/BudgetPanel.jsx";
import DecisionPanel from "./components/DecisionPanel.jsx";
import MapView from "./components/MapView.jsx";

const EVENTS = [
  ["dust_devil", "Dust devil"],
  ["local_storm", "Local storm"],
  ["regional_storm", "Regional storm"],
  ["solar_particle_event", "Solar storm"],
  ["suit_leak", "Suit leak"],
  ["fatigue", "Fatigue"],
];

export default function App() {
  const [site, setSite] = useState(null);
  const [mock, setMock] = useState(false);
  const [activeLayers, setActiveLayers] = useState(["elevation"]);
  const [route, setRoute] = useState(null);
  const [tick, setTick] = useState(null);
  const [decision, setDecision] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    getSite().then(({ data, mock }) => { setSite(data); setMock(mock); });
  }, []);

  useEffect(() => {
    if (!live) return;
    return subscribeLive((msg) => {
      if (msg.type === "tick") setTick(msg);
      else if (msg.type === "decision") setDecision(msg);
      else if (msg.type === "explanation") setExplanation(msg);
    });
  }, [live]);

  const plan = async () => {
    const target = site.targets[0];
    const { data } = await planRoute({ start: site.habitat, stops: [target.id], preset: "safe" });
    setRoute(data);
  };

  const toggleLive = () => {
    liveControl(live ? "pause" : "start", live ? {} : { speed: 10 });
    setLive((v) => !v);
  };

  const toggleLayer = (id) =>
    setActiveLayers((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  if (!site) return <p className="muted pad">Loading site…</p>;

  return (
    <div className="app">
      <header>
        <h1>Marswalk Copilot</h1>
        <span className="muted">{site.name}</span>
        {mock && <span className="badge">mock data</span>}
      </header>

      <main>
        <MapView site={site} activeLayers={activeLayers} route={route} tick={tick} decision={decision} />

        <aside>
          <section className="panel">
            <h2>Layers</h2>
            {site.layers.map((l) => (
              <label key={l.id} className="check">
                <input type="checkbox" checked={activeLayers.includes(l.id)} onChange={() => toggleLayer(l.id)} />
                {l.label}
              </label>
            ))}
          </section>

          <section className="panel">
            <h2>Simulation</h2>
            <div className="row">
              <button onClick={plan}>Plan route</button>
              <button onClick={toggleLive}>{live ? "Pause" : "Start EVA"}</button>
            </div>
            <div className="row wrap">
              {EVENTS.map(([id, label]) => (
                <button key={id} className="small" onClick={() => injectEvent(id)}>{label}</button>
              ))}
            </div>
          </section>

          <BudgetPanel route={route} tick={tick} />
          <DecisionPanel decision={decision} explanation={explanation} />
        </aside>
      </main>
    </div>
  );
}
