import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, BookOpen, Lightbulb } from 'lucide-react';
import { authService } from '@/services/auth.service';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    setLoading(true);
    try {
      const res = await authService.login({ email, password });
      login(res.user, res.access_token, res.refresh_token);
      toast.success('登录成功');
      navigate('/dashboard/chat');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen">
      {/* Left – illustration */}
      <div className="hidden flex-1 items-center justify-center bg-gradient-to-br from-primary-50 to-white p-12 lg:flex dark:from-gray-900 dark:to-gray-950">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-8 flex h-24 w-24 items-center justify-center rounded-3xl bg-primary-500 shadow-lg shadow-primary-200">
            <div className="flex">
              <BookOpen size={40} className="text-white" />
              <Lightbulb size={24} className="-ml-2 mt-5 text-yellow-300" />
            </div>
          </div>
          <h1 className="mb-3 text-3xl font-bold text-gray-800 dark:text-gray-100">
            智慧导师
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            AI 驱动的个性化教育平台，让每个学生都获得最适合的学习体验
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
            欢迎回来
          </h2>
          <p className="mb-8 text-gray-500">登录以继续你的学习之旅</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <InputField
              icon={<Mail size={16} />}
              type="email"
              placeholder="邮箱地址"
              value={email}
              onChange={setEmail}
            />
            <InputField
              icon={<Lock size={16} />}
              type={showPwd ? 'text' : 'password'}
              placeholder="密码"
              value={password}
              onChange={setPassword}
              suffix={
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              }
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-primary-500 py-2.5 text-sm font-medium text-white transition hover:bg-primary-600 active:scale-[0.98] disabled:opacity-50"
            >
              {loading ? '登录中...' : '登 录'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            还没有账号？{' '}
            <Link
              to="/register"
              className="font-medium text-primary-500 hover:text-primary-600"
            >
              去注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Reusable input ──────────────────────────────────────────── */

function InputField({
  icon,
  type,
  placeholder,
  value,
  onChange,
  suffix,
}: {
  icon: React.ReactNode;
  type: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-gray-300 bg-gray-50 px-3 py-2.5 transition focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-100 dark:border-gray-600 dark:bg-gray-800">
      <span className="text-gray-400">{icon}</span>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-400 dark:text-gray-200"
      />
      {suffix}
    </div>
  );
}
