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
    <div className="flex min-h-screen bg-[#09090b] animate-fade-in">
      {/* Left – illustration */}
      <div className="hidden flex-1 items-center justify-center p-12 relative overflow-hidden lg:flex">
        {/* Subtle blue glow blobs */}
        <div className="absolute -top-32 -left-32 h-[500px] w-[500px] rounded-full bg-primary-600/8 blur-[120px]" />
        <div className="absolute -bottom-40 -right-20 h-96 w-96 rounded-full bg-primary-400/5 blur-[100px]" />
        <div className="absolute top-1/2 left-1/3 h-72 w-72 rounded-full bg-indigo-500/4 blur-[80px]" />

        <div className="max-w-md text-center relative z-10">
          <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-600 shadow-lg glow-primary">
            <div className="flex">
              <BookOpen size={32} className="text-white" />
              <Lightbulb size={20} className="-ml-1.5 mt-4 text-primary-200" />
            </div>
          </div>
          <h1 className="font-heading mb-3 text-4xl tracking-tight text-white">
            智慧导师
          </h1>
          <p className="text-gray-500 leading-relaxed">
            AI 驱动的个性化教育平台<br />让每个学生都获得最适合的学习体验
          </p>
        </div>
      </div>

      {/* Right – form */}
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <h2 className="font-heading mb-1 text-2xl tracking-tight text-white">
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
                  className="text-gray-500 hover:text-gray-300"
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              }
            />

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-primary-600 hover:bg-primary-500 py-2.5 text-sm font-medium text-white transition-all duration-200 active:scale-[0.98] disabled:opacity-50 shadow-sm glow-primary-sm"
            >
              {loading ? '登录中...' : '登 录'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            还没有账号？{' '}
            <Link
              to="/register"
              className="font-medium text-primary-400 hover:text-primary-300 transition-colors"
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
    <div className="flex items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3 transition-all duration-200 focus-within:border-primary-500/40 focus-within:shadow-[0_0_12px_rgba(59,130,246,0.08)]">
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
  );
}
