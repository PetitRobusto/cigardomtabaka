import { create } from 'zustand';
import type { GuideSummary } from '../api';

export interface User {
  username: string;
  is_staff: boolean;
  is_superuser: boolean;
  guide?: GuideSummary;
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  checkAuth: () => Promise<void>;
  login: (username: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => Promise<void>;
}

function getCSRFToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  checkAuth: async () => {
    try {
      const res = await fetch('/api/auth/me/', {
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': getCSRFToken() },
      });
      const data = await res.json();
      if (data.authenticated) {
        set({ user: data.user, isAuthenticated: true, isLoading: false });
      } else {
        set({ user: null, isAuthenticated: false, isLoading: false });
      }
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },

  login: async (username, password) => {
    const form = new FormData();
    form.append('username', username);
    form.append('password', password);
    try {
      const res = await fetch('/api/login/', {
        method: 'POST',
        body: form,
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': getCSRFToken() },
      });
      const data = await res.json();
      if (data.ok) {
        set({ user: data.user, isAuthenticated: true });
        return { ok: true };
      }
      return { ok: false, error: data.error };
    } catch {
      return { ok: false, error: '网络错误' };
    }
  },

  logout: async () => {
    await fetch('/api/logout/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': getCSRFToken() },
    });
    set({ user: null, isAuthenticated: false });
    window.location.reload();
  },
}));
