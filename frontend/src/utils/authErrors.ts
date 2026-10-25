/** Convert API validation errors to plain text; never render error objects. */
type ApiFailure = {
  code?: string;
  response?: { status?: number; data?: { detail?: unknown } };
};

export function getAuthErrorMessage(error: unknown, fallback: string): string {
  const failure = (error ?? {}) as ApiFailure;
  if (failure.code === 'ECONNABORTED' || failure.code === 'ETIMEDOUT') {
    return '请求超时，请稍后重试；若刚才正在注册，也可以尝试登录。';
  }
  const detail = failure.response?.data?.detail;
  if (typeof detail === 'string') {
    const messages: Record<string, string> = {
      'Email already registered': '该邮箱已注册，请直接登录。',
      'Username already taken': '该用户名已被使用，请更换用户名。',
      'Invalid credentials': '邮箱或密码不正确；若尚未成功注册，请先注册。',
    };
    return messages[detail] || detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((item: unknown) => {
      if (!item || typeof item !== 'object') return '输入内容不符合要求';
      const issue = item as { loc?: unknown; type?: string; msg?: unknown };
      const field = Array.isArray(issue.loc) ? issue.loc[issue.loc.length - 1] : '';
      if (field === 'username') return '用户名需为 3–64 个字符';
      if (field === 'email') return '请输入有效的邮箱地址';
      if (field === 'password') return '密码需为 8–128 个字符';
      return typeof issue.msg === 'string' ? issue.msg : '输入内容不符合要求';
    });
    return [...new Set(messages)].join('；') || fallback;
  }
  if (failure.response?.status === 429) return '操作过于频繁，请稍后再试。';
  if (!failure.response && failure.code === 'ERR_NETWORK') return '网络连接失败，请检查网络后重试。';
  return fallback;
}

export function validateRegistration(username: string, email: string, password: string, confirmation: string): string {
  const name = username.trim();
  const address = email.trim();
  if (!name || !address || !password || !confirmation) return '请填写用户名、邮箱、密码和确认密码。';
  if ([...name].length < 3 || [...name].length > 64) return '用户名需为 3–64 个字符。';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) return '请输入有效的邮箱地址。';
  if ([...password].length < 8 || [...password].length > 128) return '密码需为 8–128 个字符。';
  if (password !== confirmation) return '两次密码不一致。';
  return '';
}
