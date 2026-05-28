import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, Plus, Trash2, Power, PowerOff, AlertTriangle, TrendingDown, TrendingUp, Activity } from 'lucide-react';
import { fetchAlerts, createAlert, updateAlert, deleteAlert, fetchSources } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { EmptyState } from '../components/shared/EmptyState';

interface AlertItem {
  id: number;
  cigar_name: string;
  source_name: string;
  condition: string;
  condition_label: string;
  target_price: number;
  enabled: boolean;
  last_triggered?: string;
}

interface Source {
  id: number;
  name: string;
}

const CONDITION_OPTIONS = [
  { value: 'below', label: '低于', icon: TrendingDown },
  { value: 'above', label: '高于', icon: TrendingUp },
  { value: 'drop_pct', label: '跌幅超(%)', icon: Activity },
];

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    cigar_id: '',
    source_id: '',
    condition: 'below',
    target_price: '',
  });

  const load = () => {
    Promise.all([fetchAlerts(), fetchSources()]).then(([a, s]) => {
      setAlerts(a.results || a || []);
      setSources(s.results || s || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.cigar_id || !form.source_id || !form.target_price) return;
    await createAlert({
      cigar: parseInt(form.cigar_id),
      source: parseInt(form.source_id),
      condition: form.condition,
      target_price: parseFloat(form.target_price),
    });
    setForm({ cigar_id: '', source_id: '', condition: 'below', target_price: '' });
    setShowForm(false);
    load();
  };

  const toggleAlert = async (alert: AlertItem) => {
    await updateAlert(alert.id, { enabled: !alert.enabled });
    load();
  };

  const removeAlert = async (id: number) => {
    await deleteAlert(id);
    load();
  };

  if (loading) return <LoadingState text="加载预警数据…" />;

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center">
            <Bell className="w-5 h-5 text-accent" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-fg">价格预警</h2>
            <p className="text-sm text-muted">当价格满足条件时自动提醒</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-accent text-white rounded-lg font-medium
            hover:bg-accent-hover active:scale-[0.98] transition-all duration-200 shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>新建预警</span>
        </button>
      </div>

      {/* Create form */}
      <AnimatePresence>
        {showForm && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.25 }}
            className="mb-6 overflow-hidden"
            onSubmit={handleSubmit}
          >
            <div className="bg-white rounded-xl border border-border shadow-sm p-5">
              <h3 className="text-sm font-semibold text-fg mb-4">新建价格预警</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">雪茄 ID</label>
                  <input
                    type="number"
                    placeholder="例如: 123"
                    value={form.cigar_id}
                    onChange={e => setForm({ ...form, cigar_id: e.target.value })}
                    required
                    className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-fg
                      placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent
                      transition-all duration-200"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">价格来源</label>
                  <select
                    value={form.source_id}
                    onChange={e => setForm({ ...form, source_id: e.target.value })}
                    required
                    className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-fg
                      focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent
                      transition-all duration-200 bg-white"
                  >
                    <option value="">选择来源</option>
                    {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">条件</label>
                  <select
                    value={form.condition}
                    onChange={e => setForm({ ...form, condition: e.target.value })}
                    className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-fg
                      focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent
                      transition-all duration-200 bg-white"
                  >
                    {CONDITION_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-1">目标价格</label>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="例如: 100.00"
                    value={form.target_price}
                    onChange={e => setForm({ ...form, target_price: e.target.value })}
                    required
                    className="w-full px-3 py-2.5 border border-border rounded-lg text-sm text-fg
                      placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent
                      transition-all duration-200"
                  />
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                <button
                  type="submit"
                  className="px-5 py-2.5 bg-accent text-white rounded-lg font-medium text-sm
                    hover:bg-accent-hover active:scale-[0.98] transition-all duration-200"
                >
                  添加预警
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-5 py-2.5 border border-border text-muted rounded-lg font-medium text-sm
                    hover:bg-accent-light transition-all duration-200"
                >
                  取消
                </button>
              </div>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* Alerts list */}
      {alerts.length === 0 ? (
        <EmptyState
          title="暂无预警规则"
          description="点击上方按钮创建第一个价格预警"
        />
      ) : (
        <div className="space-y-3">
          <AnimatePresence mode="popLayout">
            {alerts.map((alert) => (
              <motion.div
                key={alert.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98 }}
                transition={{ duration: 0.2 }}
                className={`group bg-white rounded-xl border shadow-sm overflow-hidden transition-all duration-200 ${
                  alert.enabled
                    ? 'border-border hover:border-accent hover:shadow-md'
                    : 'border-border opacity-60'
                }`}
              >
                <div className="flex items-center justify-between px-5 py-4">
                  <div className="flex items-center gap-4">
                    {/* Status indicator */}
                    <div className={`w-2 h-2 rounded-full shrink-0 ${
                      alert.enabled ? 'bg-emerald-400' : 'bg-stone-300'
                    }`} />

                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-fg text-sm">{alert.cigar_name}</span>
                        <span className="text-xs text-muted">@{alert.source_name}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-accent bg-accent-light px-2 py-0.5 rounded-full border border-accent-light">
                          {alert.condition === 'below' && <TrendingDown className="w-3 h-3" />}
                          {alert.condition === 'above' && <TrendingUp className="w-3 h-3" />}
                          {alert.condition === 'drop_pct' && <Activity className="w-3 h-3" />}
                          {alert.condition_label}
                        </span>
                        <span className="text-sm font-bold text-fg">
                          ¥{alert.target_price}
                        </span>
                        {alert.last_triggered && (
                          <span className="text-xs text-muted">
                            上次触发: {alert.last_triggered}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => toggleAlert(alert)}
                      title={alert.enabled ? '禁用' : '启用'}
                      className={`p-2 rounded-lg transition-all duration-200 ${
                        alert.enabled
                          ? 'text-emerald-600 hover:bg-emerald-50'
                          : 'text-muted hover:bg-accent-light'
                      }`}
                    >
                      {alert.enabled ? <Power className="w-4 h-4" /> : <PowerOff className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => removeAlert(alert.id)}
                      title="删除"
                      className="p-2 rounded-lg text-muted hover:text-red-500 hover:bg-red-50 transition-all duration-200"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
