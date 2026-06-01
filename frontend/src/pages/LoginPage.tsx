import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { Flame, Lock, User } from 'lucide-react';

export default function LoginPage() {
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
    <div className="min-h-screen flex items-center justify-center bg-[#1A1510]">
      <div className="w-full max-w-sm mx-4">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-lg bg-[#A04050] flex items-center justify-center mb-4">
            <Flame className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-xl font-display font-semibold text-[#FAF8F5]">Moscow Cigar</h1>
          <p className="text-sm text-[#9A8E7E] mt-1">内部管理系统</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-[#9A8E7E] mb-1.5">用户名</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9A8E7E]" />
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                required
                className="w-full pl-9 pr-4 py-2.5 bg-[#2C2416] border border-[#3D3526] rounded-md text-sm text-[#FAF8F5] placeholder:text-[#9A8E7E]/50 focus:outline-none focus:border-[#A04050] transition-colors"
                placeholder="输入用户名"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-[#9A8E7E] mb-1.5">密码</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#9A8E7E]" />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full pl-9 pr-4 py-2.5 bg-[#2C2416] border border-[#3D3526] rounded-md text-sm text-[#FAF8F5] placeholder:text-[#9A8E7E]/50 focus:outline-none focus:border-[#A04050] transition-colors"
                placeholder="输入密码"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-950/50 border border-red-800 rounded-md p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-[#A04050] text-white rounded-md text-sm font-medium hover:bg-[#8A3545] active:scale-[0.98] transition-all disabled:opacity-50"
          >
            {loading ? '登录中…' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}
