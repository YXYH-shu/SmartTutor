import api from './api';
import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  User,
} from '@/types';

export const authService = {
  async login(data: LoginRequest): Promise<TokenResponse> {
    const res = await api.post<TokenResponse>('/api/v1/auth/login', data, { timeout: 20_000 });
    return res.data;
  },

  async register(data: RegisterRequest): Promise<TokenResponse> {
    const res = await api.post<TokenResponse>('/api/v1/auth/register', data, { timeout: 20_000 });
    return res.data;
  },

  async getMe(): Promise<User> {
    const res = await api.get<User>('/api/v1/auth/me');
    return res.data;
  },

  async refreshToken(refreshToken: string): Promise<{ access_token: string }> {
    const res = await api.post('/api/v1/auth/refresh', {
      refresh_token: refreshToken,
    });
    return res.data;
  },

  async logout(): Promise<void> {
    await api.post('/api/v1/auth/logout');
  },
};
