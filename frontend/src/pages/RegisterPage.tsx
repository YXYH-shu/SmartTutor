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
    <div className="flex min-h-screen bg-[#09090b] animate-fade-in">
      {/* Left – illustration */}
      <div className="hidden flex-1 items-center justify-center p-12 relative overflow-hidden lg:flex">
        <div className="absolute -top-32 -left-32 h-[500px] w-[500px] rounded-full bg-primary-600/8 blur-[120px]" />
        <div className="absolute -bottom-40 -right-20 h-96 w-96 rounded-full bg-primary-400/5 blur-[100px]" />

        <div className="max-w-md text-center relative z-10">
          <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-600 shadow-lg glow-primary">
            <div className="flex">
              <BookOpen size={32} className="text-white" />
              <Lightbulb size={20} className="-ml-1.5 mt-4 text-primary-200" />
            </div>
          </div>
          <h1 className="font-heading mb-3 text-3xl tracking-tight text-white">
            智慧导师
          </h1>
          <p className="text-gray-500">
            注册即开启 AI 个性化学习旅程
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="font-heading mb-1 text-2xl tracking-tight text-white">
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
                    className="text-gray-500 hover:text-gray-300"
                  >
                    {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                }
              />
              {password && (
                <div className="mt-2 flex gap-1">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div
                      key={i}
                      className={cn(
                        'h-1 flex-1 rounded-full transition-colors',
                        i < strength.level
                          ? strength.color
                          : 'bg-white/5',
                      )}
                    />
                  ))}
                  <span className="ml-2 text-xs text-gray-500">
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
              className="w-full rounded-xl bg-primary-600 hover:bg-primary-500 py-2.5 text-sm font-medium text-white transition-all duration-200 active:scale-[0.98] disabled:opacity-50 shadow-sm glow-primary-sm"
            >
              {loading ? '注册中...' : '注 册'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            已有账号？{' '}
            <Link
              to="/login"
              className="font-medium text-primary-400 hover:text-primary-300 transition-colors"
            >
              去登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

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
          'flex items-center gap-2 rounded-xl border bg-white/[0.03] px-4 py-3 transition-all duration-200',
          error
            ? 'border-red-500/40'
            : 'border-white/[0.08] focus-within:border-primary-500/40 focus-within:shadow-[0_0_12px_rgba(59,130,246,0.08)]',
        )}
      >
        <span className="text-gray-500">{icon}</span>
        <input
          type={type}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 bg-transparent text-sm text-gray-200 outline-none placeholder:text-gray-600"
        />
        {suffix}
      </div>
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
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
    { level: 1, label: '弱', color: 'bg-red-500' },
    { level: 2, label: '一般', color: 'bg-yellow-500' },
    { level: 3, label: '较强', color: 'bg-primary-400' },
    { level: 4, label: '强', color: 'bg-green-500' },
  ];
  return levels[score];
}
