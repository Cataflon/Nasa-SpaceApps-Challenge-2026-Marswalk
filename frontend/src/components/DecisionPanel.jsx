// Decizia curentă (apare imediat) + explicația (vine separat, de la LLM sau din șablon).
export default function DecisionPanel({ decision, explanation }) {
  if (!decision) return <section className="panel"><h2>Copilot</h2><p className="muted">Niciun eveniment încă.</p></section>;

  return (
    <section className="panel">
      <h2>Copilot · t+{decision.t_min} min</h2>
      <div className={`decision ${decision.decision}`}>{decision.decision}</div>
      <p className="explanation">
        {explanation?.decision_id === decision.decision_id ? explanation.text : <span className="muted">se gândește…</span>}
        {explanation?.decision_id === decision.decision_id && <small> ({explanation.source})</small>}
      </p>
      <table>
        <thead><tr><th>Variantă</th><th>+min</th><th>O₂ final</th><th>Risc</th><th></th></tr></thead>
        <tbody>
          {decision.alternatives.map((a) => (
            <tr key={a.id} className={a.id === decision.alternative_id ? "chosen" : a.valid ? "" : "invalid"}>
              <td>{a.id}</td>
              <td>{a.extra_min}</td>
              <td>{a.o2_end_pct}%</td>
              <td>{a.risk}</td>
              <td>{a.valid ? (a.id === decision.alternative_id ? "✔ aleasă" : "") : `✖ ${a.violations.join(", ")}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
