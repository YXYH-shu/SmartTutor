import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, BookOpen, Lightbulb } from 'lucide-react';
import { authService } from '@/services/auth.service';
import { useAuthStore } from '@/stores/authStore';
import { toast } from 'sonner';
import { getAuthErrorMessage } from '@/utils/authErrors';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setErrorMessage('');
    if (!email.trim() || !password) {
      setErrorMessage('请填写邮箱和密码。');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setErrorMessage('请输入有效的邮箱地址。');
      return;
    }

    setLoading(true);
    try {
      const res = await authService.login({ email: email.trim(), password });
      login(res.user, res.access_token, res.refresh_token);
      toast.success('登录成功');
      navigate('/dashboard/chat');
    } catch (err: unknown) {
      setErrorMessage(getAuthErrorMessage(err, '登录失败，请稍后重试。'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-bg-base animate-fade-in">
      {/* Left – illustration */}
      <div className="hidden flex-1 items-center justify-center p-12 relative overflow-hidden lg:flex">
        {/* 单一暖金微光晕装饰(替代原 3 个蓝色 blob) */}
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
          <p className="text-text-tertiary leading-relaxed">
            AI 驱动的个性化教育平台<br />让每个学生都获得最适合的学习体验
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="font-heading mb-1 text-24 tracking-tight text-text-primary">
            欢迎回来
          </h2>
          <p className="mb-8 text-text-tertiary">登录以继续你的学习之旅</p>

          <form onSubmit={handleSubmit} noValidate aria-busy={loading} className="space-y-4">
            {errorMessage && <p role="alert" className="text-14 text-status-error">{errorMessage}</p>}
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
                  className="text-text-tertiary hover:text-text-secondary"
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              }
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-accent hover:bg-accent/90 py-2.5 text-14 font-medium text-white transition-all duration-200 active:scale-[0.98] disabled:opacity-50 shadow-sm glow-primary-sm"
            >
              {loading ? '登录中...' : '登 录'}
            </button>
          </form>

          <p className="mt-6 text-center text-14 text-text-tertiary">
            还没有账号？{' '}
            <Link
              to="/register"
              className="font-medium text-accent hover:text-accent/80 transition-colors"
            >
              去注册
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

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
    <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-bg-elevated px-4 py-3 transition-all duration-200 focus-within:border-accent/40 focus-within:shadow-[0_0_12px_var(--color-accent-glow)]">
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
  );
}
