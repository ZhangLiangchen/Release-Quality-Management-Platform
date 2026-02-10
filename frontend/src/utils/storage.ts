import type { User } from '../domain/types';

export const STORAGE_KEYS = {
  token: 'qms.accessToken',
  user: 'qms.currentUser',
  viewVersionKey: 'qms.viewVersionKey',
} as const;

export function storeAuth(token: string, user: User): void {
  localStorage.setItem(STORAGE_KEYS.token, token);
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
}

export function loadAuth(): { token: string; user: User } | null {
  const token = localStorage.getItem(STORAGE_KEYS.token);
  const rawUser = localStorage.getItem(STORAGE_KEYS.user);
  if (!token || !rawUser) {
    return null;
  }

  try {
    const user = JSON.parse(rawUser) as User;
    return { token, user };
  } catch {
    clearAuth();
    return null;
  }
}

export function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEYS.token);
  localStorage.removeItem(STORAGE_KEYS.user);
}

export function loadViewVersionKey(): string | null {
  return localStorage.getItem(STORAGE_KEYS.viewVersionKey);
}

export function storeViewVersionKey(versionKey: string): void {
  localStorage.setItem(STORAGE_KEYS.viewVersionKey, versionKey);
}
