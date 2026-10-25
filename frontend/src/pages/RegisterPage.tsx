import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { User, Mail, Lock, Eye, EyeOff, BookOpen, Lightbulb } from 'lucide-react';
import { authService } from '@/services/auth.service';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';
import { cn } from '@/utils/cn';
import { getAuthErrorMessage, validateRegistration } from '@/utils/authErrors';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const strength = getStrength(password);
  const passwordsMatch = password === confirmPwd;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setErrorMessage('');
    const validation = validateRegistration(username, email, password, confirmPwd);
    if (validation) {
      setErrorMessage(validation);
      return;
    }

    setLoading(true);
    try {
      const res = await authService.register({
        username: username.trim(),
        email: email.trim(),
        password,
      });
      login(res.user, res.access_token, res.refresh_token);
      toast.success('注册成功！');
      navigate('/dashboard/chat');
    } catch (err: unknown) {
      setErrorMessage(getAuthErrorMessage(err, '注册失败，请稍后重试。'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-bg-base animate-fade-in">
      {/* Left – illustration */}
      <div className="hidden flex-1 items-center justify-center p-12 relative overflow-hidden lg:flex">
        {/* 单一暖金微光晕装饰(替代原 2 个蓝色 blob) */}
        <div className="pointer-events-none absolute -top-40 left-1/4 h-96 w-96 rounded-full bg-accent/10 blur-3xl" />

        <div className="max-w-md text-center relative z-10">
          <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-xl bg-accent shadow-lg glow-primary">
            <div className="flex">
              <BookOpen size={32} className="text-white" />
              <Lightbulb size={20} className="-ml-1.5 mt-4 text-accent/80" />
            </div>
          </div>
          <h1 className="font-heading mb-3 text-32 tracking-tight text-text-primary">
            智慧导师
          </h1>
          <p className="text-text-tertiary">
            注册即开启 AI 个性化学习旅程
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="font-heading mb-1 text-24 tracking-tight text-text-primary">
            创建账号
          </h2>
          <p className="mb-8 text-text-tertiary">开始你的智能学习之旅</p>

          <form onSubmit={handleSubmit} noValidate aria-busy={loading} className="space-y-4">
            {errorMessage && <p role="alert" className="text-14 text-status-error">{errorMessage}</p>}
            <Field
              icon={<User size={16} />}
              type="text"
              placeholder="用户名（3–64个字符）"
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
                    className="text-text-tertiary hover:text-text-secondary"
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
                  <span className="ml-2 text-12 text-text-tertiary">
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
              disabled={loading}
              className="w-full rounded-xl bg-accent hover:bg-accent/90 py-2.5 text-14 font-medium text-white transition-all duration-200 active:scale-[0.98] disabled:opacity-50 shadow-sm glow-primary-sm"
            >
              {loading ? '注册中...' : '注 册'}
            </button>
          </form>

          <p className="mt-6 text-center text-14 text-text-tertiary">
            已有账号？{' '}
            <Link
              to="/login"
              className="font-medium text-accent hover:text-accent/80 transition-colors"
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
          'flex items-center gap-2 rounded-xl border bg-bg-elevated px-4 py-3 transition-all duration-200',
          error
            ? 'border-status-error/40'
            : 'border-border-subtle focus-within:border-accent/40 focus-within:shadow-[0_0_12px_var(--color-accent-glow)]',
        )}
      >
        <span className="text-text-tertiary">{icon}</span>
        <input
          type={type}
          placeholder={placeholder}
          aria-label={placeholder}
          required
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 bg-transparent text-14 text-text-primary outline-none placeholder:text-text-tertiary"
        />
        {suffix}
      </div>
      {error && <p className="mt-1 text-12 text-status-error">{error}</p>}
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
    { level: 1, label: '弱', color: 'bg-status-error' },
    { level: 2, label: '一般', color: 'bg-status-warning' },
    { level: 3, label: '较强', color: 'bg-status-info' },
    { level: 4, label: '强', color: 'bg-status-success' },
  ];
  return levels[score];
}
