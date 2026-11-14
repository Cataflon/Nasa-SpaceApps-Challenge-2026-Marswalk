import { useEffect, useRef, useState } from 'react';
import text from '../../../docs/how-we-calculate.md?raw';
import { streamChat } from '../api/client';
function inline(value) { return value.split(/(\*\*.*?\*\*|`.*?`)/).map((s, i) => s.startsWith('**') ? <strong key={i}>{s.slice(2, -2)}</strong> : s.startsWith('`') ? <code key={i}>{s.slice(1, -1)}</code> : s); }
export function Information() {
  const lines = text.split('\n'), blocks = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (line.startsWith('|')) { const rows = []; while (i < lines.length && lines[i].trim().startsWith('|')) { const row = lines[i++].trim(); if (!/^\|[\s:|\-]+\|$/.test(row)) rows.push(row.split('|').slice(1, -1)); } i--; blocks.push(<div className="table-scroll" key={i}><table><thead><tr>{rows[0].map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead><tbody>{rows.slice(1).map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody></table></div>); }
    else if (/^#{1,6} /.test(line)) { const Tag = `h${Math.min(3, line.match(/^#+/)[0].length)}`; blocks.push(<Tag key={i}>{inline(line.replace(/^#+ /, ''))}</Tag>); }
    else if (/^[-*] /.test(line)) blocks.push(<p key={i} className="doc-list">• {inline(line.slice(2))}</p>);
    else if (/^---+$/.test(line)) blocks.push(<hr key={i}/>);
    else blocks.push(<p key={i}>{inline(line)}</p>);
  }
  return <article className="information-page">{blocks}</article>;
}
export function Chat({ mock, onRoute, disabled }) {
  const [message, setMessage] = useState(''), [messages, setMessages] = useState([]), [response, setResponse] = useState(''), [tools, setTools] = useState([]), [loading, setLoading] = useState(false), [error, setError] = useState('');
  const abort = useRef(null);
  useEffect(() => () => abort.current?.abort(), []);
  async function send(e) {
    e.preventDefault(); if (!message.trim() || loading) return;
    const prompt = message.trim(); setMessage(''); setResponse(''); setTools([]); setError(''); setLoading(true); abort.current = new AbortController(); let output = '';
    const history = messages.slice(-10); setMessages(m => [...m, { role: 'user', content: prompt }]);
    try { await streamChat(prompt, history, item => { if (item.type === 'token') { output += item.text; setResponse(output); } if (item.type === 'tool_call') setTools(t => [...t, item.name]); if (item.type === 'route' && Array.isArray(item.route?.path)) onRoute({ data: item.route, mock }); }, abort.current.signal, mock); setMessages(m => [...m, { role: 'assistant', content: output }]); } catch (e) { if (e.name !== 'AbortError') setError(e.message); } finally { setLoading(false); }
  }
  return <section className="chat-panel"><h3>Ask the copilot</h3><p className="small muted">{mock?'Demo: recorded mission advice.':'Mission advice based on the available mission data.'}</p><div className="chat-history">{messages.slice(-6).map((m,i)=><p key={i} className={`chat-message ${m.role}`}>{m.content}</p>)}{loading&&<p aria-live="polite">{response||'Preparing response?'}</p>}</div>{tools.length>0&&<p className="tool-label">Tools: {tools.join(', ')}</p>}{error&&<p role="alert" className="error">{error}</p>}<form onSubmit={send}><label className="sr-only" htmlFor="chat-message">Message to copilot</label><input id="chat-message" value={message} onChange={e=>setMessage(e.target.value)} disabled={disabled} placeholder="What should I consider for this EVA?" maxLength={2000}/><button className="button primary" disabled={loading||disabled||!message.trim()}>Send</button></form>{disabled&&<p className="small muted">Reset the simulation before requesting a new plan through chat.</p>}</section>;
}
