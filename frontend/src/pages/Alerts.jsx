import { useState, useEffect } from 'react';
import { fetchAlerts, createAlert, updateAlert, deleteAlert, fetchSources } from '../api';

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ cigar_id: '', source_id: '', condition: 'below', target_price: '' });

  const load = () => {
    Promise.all([fetchAlerts(), fetchSources()]).then(([a, s]) => {
      setAlerts(a.results || a);
      setSources(s.results || s);
      setLoading(false);
    });
  };

  useEffect(() => { load(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.cigar_id || !form.source_id || !form.target_price) return;
    await createAlert({
      cigar: parseInt(form.cigar_id),
      source: parseInt(form.source_id),
      condition: form.condition,
      target_price: parseFloat(form.target_price),
    });
    setForm({ cigar_id: '', source_id: '', condition: 'below', target_price: '' });
    load();
  };

  const toggleAlert = async (alert) => {
    await updateAlert(alert.id, { enabled: !alert.enabled });
    load();
  };

  const removeAlert = async (id) => {
    await deleteAlert(id);
    load();
  };

  if (loading) return <div className="loading">加载中...</div>;

  return (
    <div className="alerts-page">
      <h2>价格预警</h2>

      {/* Create form */}
      <form className="alert-form" onSubmit={handleSubmit}>
        <input
          type="number" placeholder="雪茄 ID" value={form.cigar_id}
          onChange={e => setForm({ ...form, cigar_id: e.target.value })}
          required
        />
        <select value={form.source_id} onChange={e => setForm({ ...form, source_id: e.target.value })} required>
          <option value="">选择来源</option>
          {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select value={form.condition} onChange={e => setForm({ ...form, condition: e.target.value })}>
          <option value="below">低于</option>
          <option value="above">高于</option>
          <option value="drop_pct">跌幅超(%)</option>
        </select>
        <input
          type="number" step="0.01" placeholder="目标价格" value={form.target_price}
          onChange={e => setForm({ ...form, target_price: e.target.value })}
          required
        />
        <button type="submit">添加预警</button>
      </form>

      {/* Alerts list */}
      <div className="alerts-list">
        {alerts.length === 0 && <div className="empty">暂无预警</div>}
        {alerts.map(a => (
          <div key={a.id} className={`alert-item ${a.enabled ? '' : 'disabled'}`}>
            <div className="alert-info">
              <span className="alert-cigar">{a.cigar_name}</span>
              <span className="alert-source">@{a.source_name}</span>
              <span className="alert-cond">{a.condition_label}</span>
              <span className="alert-price">{a.target_price}</span>
              {a.last_triggered && <span className="alert-triggered">上次触发: {a.last_triggered}</span>}
            </div>
            <div className="alert-actions">
              <button onClick={() => toggleAlert(a)}>{a.enabled ? '禁用' : '启用'}</button>
              <button className="danger" onClick={() => removeAlert(a.id)}>删除</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
