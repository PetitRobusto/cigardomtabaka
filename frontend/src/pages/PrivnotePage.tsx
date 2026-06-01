import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link2, Clock, Lock, Flame, Copy, Check } from 'lucide-react';
import { fetchBrandList, createPrivnote } from '../api';
import { LoadingState } from '../components/shared/LoadingState';
import { useAuthStore } from '../store/authStore';

const DURATIONS = [
  { value: '1', label: '1 小时' },
  { value: '6', label: '6 小时' },
  { value: '24', label: '24 小时' },
  { value: '72', label: '3 天' },
  { value: '168', label: '7 天' },
  { value: '720', label: '30 天' },
];

export default function PrivnotePage() {
  const { user } = useAuthStore();
  const [noteType, setNoteType] = useState('catalog');
  const [duration, setDuration] = useState('24');
  const [password, setPassword] = useState('');
  const [burn, setBurn] = useState(true);
  const [result, setResult] = useState<{ url: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: brandsData } = useQuery({
    queryKey: ['brands'],
    queryFn: fetchBrandList,
    enabled: false,
  });

  if (!user?.is_staff) {
    return (
      <div className="text-center py-20">
        <p className="text-muted">您没有权限访问此页面</p>
      </div>
    );
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const form = new FormData();
    form.append('note_type', noteType);
    form.append('duration', duration);
    form.append('password', password);
    form.append('burn', burn ? 'on' : 'off');
    try {
      const res = await createPrivnote(form);
      if (res.url) setResult({ url: res.url, token: res.token });
    } finally {
      setLoading(false);
    }
  };

  const copyUrl = () => {
    if (result?.url) {
      navigator.clipboard.writeText(result.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="animate-fade-in max-w-xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-accent/10 flex items-center justify-center">
          <Link2 className="w-5 h-5 text-accent" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-fg">生成链接</h1>
          <p className="text-sm text-muted">创建一次性客户文档</p>
        </div>
      </div>

      {result ? (
        <div className="bg-white border border-border rounded-md p-6 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-4">
            <Check className="w-6 h-6 text-emerald-600" />
          </div>
          <h3 className="text-lg font-semibold text-fg mb-2">链接已生成</h3>
          <div className="flex items-center gap-2 bg-accent-light rounded-md p-3 mb-4">
            <code className="text-sm text-fg flex-1 break-all">{result.url}</code>
            <button
              onClick={copyUrl}
              className="p-2 rounded-md text-accent hover:bg-accent/10 transition-colors shrink-0"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <button
            onClick={() => { setResult(null); setPassword(''); }}
            className="text-sm text-accent hover:underline"
          >
            创建新的链接
          </button>
        </div>
      ) : (
        <form onSubmit={handleCreate} className="bg-white border border-border rounded-md p-5 space-y-5">
          {/* Note Type */}
          <div>
            <label className="block text-sm font-medium text-fg mb-2">场景</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setNoteType('catalog')}
                className={`flex-1 py-2.5 rounded-md text-sm font-medium transition-all ${
                  noteType === 'catalog'
                    ? 'bg-accent text-white'
                    : 'bg-accent-light text-fg hover:bg-accent/10'
                }`}
              >
                库存展示
              </button>
              <button
                type="button"
                onClick={() => setNoteType('sales')}
                className={`flex-1 py-2.5 rounded-md text-sm font-medium transition-all ${
                  noteType === 'sales'
                    ? 'bg-accent text-white'
                    : 'bg-accent-light text-fg hover:bg-accent/10'
                }`}
              >
                销售单据
              </button>
            </div>
          </div>

          {/* Duration */}
          <div>
            <label className="flex items-center gap-1.5 text-sm font-medium text-fg mb-2">
              <Clock className="w-4 h-4" />
              有效期
            </label>
            <select
              value={duration}
              onChange={e => setDuration(e.target.value)}
              className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
            >
              {DURATIONS.map(d => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </div>

          {/* Password */}
          <div>
            <label className="flex items-center gap-1.5 text-sm font-medium text-fg mb-2">
              <Lock className="w-4 h-4" />
              密码保护（可选）
            </label>
            <input
              type="text"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="留空则不设密码"
              className="w-full px-3 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent"
            />
          </div>

          {/* Burn after read */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Flame className="w-4 h-4 text-accent" />
              <span className="text-sm font-medium text-fg">阅后即焚</span>
            </div>
            <button
              type="button"
              onClick={() => setBurn(!burn)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                burn ? 'bg-accent' : 'bg-border'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  burn ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {loading ? '生成中…' : '生成链接'}
          </button>
        </form>
      )}
    </div>
  );
}
