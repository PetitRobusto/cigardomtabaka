import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { Lock, User } from 'lucide-react';
import { usePageMeta } from '../hooks/usePageMeta';

const base = import.meta.env.BASE_URL;

export default function LoginPage() {
  const { setMeta } = usePageMeta();

  useEffect(() => {
    setMeta({
      title: '登录',
      breadcrumbs: [{ label: '登录' }],
    });
  }, [setMeta]);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    const result = await login(username, password);
    setLoading(false);
    if (result.ok) {
      navigate('/');
    } else {
      setError(result.error || '登录失败');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cream">
      <div className="w-full max-w-sm mx-4">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <img src={`${base}logo-120.png`} alt="CigarDomTabaka" className="w-[120px] h-[120px] mb-4 object-contain" />
          <h1 className="text-xl font-display font-semibold text-fg">CigarDomTabaka</h1>
          <p className="text-sm text-muted mt-1">内部管理系统</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-muted mb-1.5">用户名</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                className="w-full pl-9 pr-4 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted/50 focus:outline-none focus:border-accent transition-colors"
                placeholder="输入用户名"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-muted mb-1.5">密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted" />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full pl-9 pr-4 py-2.5 bg-white border border-border rounded-md text-sm text-fg placeholder:text-muted/50 focus:outline-none focus:border-accent transition-colors"
                placeholder="输入密码"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-300 rounded-md p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-accent text-white rounded-md text-sm font-medium hover:bg-accent-hover active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {loading ? '登录中…' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}
