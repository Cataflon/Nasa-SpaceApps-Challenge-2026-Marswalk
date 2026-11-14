// Harta: straturile ca imagini + suprapuneri SVG în coordonate de grilă (x = col, y = row).
const ALT_COLORS = { REROUTE: "#4fb3ff", WAIT: "#f2c14e", RETURN: "#b48cff", CONTINUE: "#ffffff" };

const points = (path) => path.map(([r, c]) => `${c},${r}`).join(" ");

export default function MapView({ site, activeLayers, route, tick, decision }) {
  const [rows, cols] = site.shape;
  const cell = site.cell_size_m;

  return (
    <svg className="map" viewBox={`0 0 ${cols} ${rows}`} preserveAspectRatio="xMidYMid meet">
      <rect width={cols} height={rows} fill="#3a2418" />
      {site.layers
        .filter((l) => activeLayers.includes(l.id))
        .map((l) => (
          <image key={l.id} href={l.png} width={cols} height={rows} preserveAspectRatio="none" />
        ))}

      {route && <polyline points={points(route.path)} className="route-planned" />}

      {decision?.alternatives?.map((a) => (
        <polyline
          key={a.id}
          points={points(a.path)}
          stroke={ALT_COLORS[a.kind] ?? "#fff"}
          className={`route-alt ${a.valid ? "" : "invalid"} ${a.id === decision.alternative_id ? "chosen" : ""}`}
        />
      ))}

      {tick?.hazards?.map((h) => (
        <g key={h.id}>
          {h.forecast?.map((f) => (
            <ellipse key={f.t_min} cx={f.center.col} cy={f.center.row} rx={f.axes_m[0] / cell} ry={f.axes_m[1] / cell}
              transform={`rotate(${h.angle_deg} ${f.center.col} ${f.center.row})`} className="hazard-forecast" />
          ))}
          <ellipse cx={h.center.col} cy={h.center.row} rx={h.axes_m[0] / cell} ry={h.axes_m[1] / cell}
            transform={`rotate(${h.angle_deg} ${h.center.col} ${h.center.row})`} className="hazard" style={{ opacity: 0.25 + 0.5 * h.intensity }} />
        </g>
      ))}

      {tick?.point_of_no_return && (
        <circle cx={tick.point_of_no_return.col} cy={tick.point_of_no_return.row} r={4} className="pnr" />
      )}

      <rect x={site.habitat.col - 4} y={site.habitat.row - 4} width={8} height={8} className="habitat" />
      {site.targets.map((t) => (
        <g key={t.id}>
          <circle cx={t.col} cy={t.row} r={4} className={`target ${t.kind}`} />
          <text x={t.col + 6} y={t.row + 3} className="label">{t.name}</text>
        </g>
      ))}

      {tick?.astronaut && <circle cx={tick.astronaut.col} cy={tick.astronaut.row} r={5} className="astronaut" />}
    </svg>
  );
}
