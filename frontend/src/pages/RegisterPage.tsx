import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { User, Mail, Lock, Eye, EyeOff, BookOpen, Lightbulb } from 'lucide-react';
import { authService } from '@/services/auth.service';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';
import { cn } from '@/utils/cn';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);

  const strength = getStrength(password);
  const passwordsMatch = password === confirmPwd;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username || !email || !password || !confirmPwd) return;
    if (!passwordsMatch) {
      toast.error('两次密码不一致');
      return;
    }

    setLoading(true);
    try {
      const res = await authService.register({
        username,
        email,
        password,
      });
      login(res.user, res.access_token, res.refresh_token);
      toast.success('注册成功！');
      navigate('/dashboard/chat');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || '注册失败');
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
            注册即开启 AI 个性化学习旅程
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
            创建账号
          </h2>
          <p className="mb-8 text-gray-500">开始你的智能学习之旅</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Field
              icon={<User size={16} />}
              type="text"
              placeholder="用户名"
              value={username}
              onChange={setUsername}
            />
            <Field
              icon={<Mail size={16} />}
              type="email"
              placeholder="邮箱地址"
              value={email}
              onChange={setEmail}
            />
            <div>
              <Field
                icon={<Lock size={16} />}
                type={showPwd ? 'text' : 'password'}
                placeholder="密码（至少8位）"
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
              {/* Password strength bar */}
              {password && (
                <div className="mt-2 flex gap-1">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className={cn(
                        'h-1 flex-1 rounded-full transition-colors',
                        i < strength.level
                          ? strength.color
                          : 'bg-gray-200 dark:bg-gray-700',
                      )}
                    />
                  ))}
                  <span className="ml-2 text-xs text-gray-400">
                    {strength.label}
                  </span>
                </div>
              )}
            </div>
            <Field
              icon={<Lock size={16} />}
              type="password"
              placeholder="确认密码"
              value={confirmPwd}
              onChange={setConfirmPwd}
              error={confirmPwd && !passwordsMatch ? '密码不一致' : undefined}
            />

            <button
              type="submit"
              disabled={loading || !passwordsMatch}
              className="w-full rounded-xl bg-primary-500 py-2.5 text-sm font-medium text-white transition hover:bg-primary-600 active:scale-[0.98] disabled:opacity-50"
            >
              {loading ? '注册中...' : '注 册'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            已有账号？{' '}
            <Link
              to="/login"
              className="font-medium text-primary-500 hover:text-primary-600"
            >
              去登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Helper ──────────────────────────────────────────────────── */

function Field({
  icon,
  type,
  placeholder,
  value,
  onChange,
  suffix,
  error,
}: {
  icon: React.ReactNode;
  type: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: React.ReactNode;
  error?: string;
}) {
  return (
    <div>
      <div
        className={cn(
          'flex items-center gap-2 rounded-xl border bg-gray-50 px-3 py-2.5 transition',
          error
            ? 'border-red-400'
            : 'border-gray-300 focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-100 dark:border-gray-600 dark:focus-within:border-primary-500',
          'dark:bg-gray-800',
        )}
      >
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
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}

function getStrength(pwd: string) {
  let score = 0;
  if (pwd.length >= 8) score++;
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score++;
  if (/\d/.test(pwd)) score++;
  if (/[^a-zA-Z0-9]/.test(pwd)) score++;

  const levels = [
    { level: 0, label: '', color: '' },
    { level: 1, label: '弱', color: 'bg-red-400' },
    { level: 2, label: '一般', color: 'bg-yellow-400' },
    { level: 3, label: '较强', color: 'bg-primary-400' },
    { level: 4, label: '强', color: 'bg-green-500' },
  ];
  return levels[score];
}
