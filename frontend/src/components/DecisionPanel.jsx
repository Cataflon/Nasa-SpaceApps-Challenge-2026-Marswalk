import { alternatives, decisions, number, violation } from '../utils';
import Icon from './Icon';
export default function DecisionPanel({ live, route }) {
  const decision = live.decision, explanation = decision && live.explanations[decision.decision_id];
  return <section className="copilot-section"><div className="section-title"><h3><Icon name="shield" size={17}/> Copilot</h3><span className="small muted">{decision ? `t+${decision.t_min}` : 'În așteptare'}</span></div>
    <div className={`decision-title ${decision?.decision ?? ''}`}>{decision ? decisions[decision.decision] ?? decision.decision : route ? 'Pregătit de explorare' : 'Începe cu un plan'}</div>
    <p className="decision-description" aria-live="polite">{decision ? explanation?.text ?? 'Decizia este aplicată. Se pregătește explicația…' : route ? 'Traseul este pregătit. Pornește simularea pentru a urmări ieșirea.' : 'Alege opririle și durata. Copilotul va urmări traseul și condițiile misiunii.'}</p>
    {explanation && <span className="source-label">Explicație: {({ llm: 'LLM', template: 'șablon', cache: 'cache' })[explanation.source] ?? explanation.source}</span>}
    {decision && <details className="alternatives"><summary>Compară {decision.alternatives?.length ?? 0} alternative</summary><div className="table-scroll"><table><thead><tr><th>Variantă</th><th>O₂ final</th><th>Rezultat</th></tr></thead><tbody>{decision.alternatives?.map(a => <tr key={a.id} className={a.id === decision.alternative_id ? 'chosen' : ''}><td>{alternatives[a.id] ?? a.id}<small>+{number(a.extra_min)} min</small></td><td>{number(a.o2_end_pct, 1)}%</td><td>{!a.valid ? a.violations.map(violation).join(', ') : a.id === decision.alternative_id ? 'Aleasă' : 'Validă'}</td></tr>)}</tbody></table></div></details>}
    {live.history.length > 1 && <details><summary>Istoric decizii ({live.history.length})</summary>{live.history.map(d => <p className="small history-row" key={d.decision_id}>t+{d.t_min} <strong>{decisions[d.decision]}</strong><br/>{live.explanations[d.decision_id]?.text ?? 'Explicație în așteptare'}</p>)}</details>}
  </section>;
}
