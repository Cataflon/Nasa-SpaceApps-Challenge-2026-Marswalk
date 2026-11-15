import { alternatives, decisions, number, violation } from '../utils';
import Icon from './Icon';
export default function DecisionPanel({ live, route }) {
  const decision = live.decision, explanation = decision && live.explanations[decision.decision_id];
  return <section className="copilot-section"><div className="section-title"><h3><Icon name="shield" size={17}/> Copilot</h3><span className="small muted">{decision ? `t+${decision.t_min}` : 'Standing by'}</span></div>
    <div className={`decision-title ${decision?.decision ?? ''}`}>{decision ? decisions[decision.decision] ?? decision.decision : route ? 'Ready to explore' : 'Start with a plan'}</div>
    <p className="decision-description" aria-live="polite">{decision ? explanation?.text ?? 'Decision applied. Preparing the explanation…' : route ? 'Route ready. Start the simulation to follow the EVA.' : 'Choose stops and duration. The copilot will watch the route and mission conditions.'}</p>
    {explanation && <span className="source-label">Explanation: {({ llm: 'LLM', template: 'template', cache: 'cache' })[explanation.source] ?? explanation.source}</span>}
    {decision && <details className="alternatives"><summary>Compare {decision.alternatives?.length ?? 0} options</summary><div className="table-scroll"><table><thead><tr><th>Option</th><th>Final O₂</th><th>Result</th></tr></thead><tbody>{decision.alternatives?.map(a => <tr key={a.id} className={a.id === decision.alternative_id ? 'chosen' : ''}><td>{alternatives[a.id] ?? a.id}<small>+{number(a.extra_min)} min</small></td><td>{number(a.o2_end_pct, 1)}%</td><td>{!a.valid ? a.violations.map(violation).join(', ') : a.id === decision.alternative_id ? 'Chosen' : 'Valid'}</td></tr>)}</tbody></table></div></details>}
    {live.history.length > 1 && <details><summary>Decision history ({live.history.length})</summary>{live.history.map(d => <p className="small history-row" key={d.decision_id}>t+{d.t_min} <strong>{decisions[d.decision]}</strong><br/>{live.explanations[d.decision_id]?.text ?? 'Explanation pending'}</p>)}</details>}
  </section>;
}
