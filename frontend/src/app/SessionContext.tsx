import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { repository as defaultRepository } from '../data';
import type { Repository } from '../data/repository';
import type { LoginPayload, ProjectConfig, User, Version } from '../domain/types';
import { clearAuth, loadAuth, loadViewVersionKey, storeAuth, storeViewVersionKey } from '../utils/storage';

interface SessionContextValue {
  repository: Repository;
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  bootstrapLoading: boolean;
  config: ProjectConfig | null;
  versions: Version[];
  viewVersionKey: string | null;
  login: (payload: LoginPayload) => Promise<void>;
  logout: () => void;
  refreshBootstrap: () => Promise<void>;
  setViewVersion: (versionKey: string) => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

interface SessionProviderProps {
  children: ReactNode;
  repository?: Repository;
}

export function SessionProvider({ children, repository = defaultRepository }: SessionProviderProps) {
  const [loading, setLoading] = useState(true);
  const [bootstrapLoading, setBootstrapLoading] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [config, setConfig] = useState<ProjectConfig | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [viewVersionKey, setViewVersionKey] = useState<string | null>(null);

  const syncViewVersion = useCallback((nextConfig: ProjectConfig, nextVersions: Version[]) => {
    const storedVersion = loadViewVersionKey();
    const hasStored = storedVersion ? nextVersions.some((item) => item.versionKey === storedVersion) : false;

    if (hasStored && storedVersion) {
      setViewVersionKey(storedVersion);
      return;
    }

    setViewVersionKey(nextConfig.currentVersionKey);
    storeViewVersionKey(nextConfig.currentVersionKey);
  }, []);

  const refreshBootstrap = useCallback(async () => {
    if (!user) {
      return;
    }

    setBootstrapLoading(true);
    try {
      const [nextConfig, nextVersions] = await Promise.all([repository.getConfig(), repository.listVersions()]);
      setConfig(nextConfig);
      setVersions(nextVersions);
      syncViewVersion(nextConfig, nextVersions);
    } finally {
      setBootstrapLoading(false);
    }
  }, [repository, syncViewVersion, user]);

  useEffect(() => {
    const saved = loadAuth();

    if (!saved) {
      setLoading(false);
      return;
    }

    setToken(saved.token);
    setUser(saved.user);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refreshBootstrap();
  }, [refreshBootstrap]);

  const login = useCallback(
    async (payload: LoginPayload) => {
      const result = await repository.login(payload);
      storeAuth(result.accessToken, result.user);
      setToken(result.accessToken);
      setUser(result.user);
    },
    [repository],
  );

  const logout = useCallback(() => {
    clearAuth();
    setToken(null);
    setUser(null);
    setConfig(null);
    setVersions([]);
    setViewVersionKey(null);
  }, []);

  const setViewVersion = useCallback((versionKey: string) => {
    setViewVersionKey(versionKey);
    storeViewVersionKey(versionKey);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      repository,
      user,
      token,
      isAuthenticated: Boolean(user && token),
      loading,
      bootstrapLoading,
      config,
      versions,
      viewVersionKey,
      login,
      logout,
      refreshBootstrap,
      setViewVersion,
    }),
    [bootstrapLoading, config, loading, login, logout, refreshBootstrap, repository, token, user, versions, viewVersionKey, setViewVersion],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used inside SessionProvider');
  }
  return context;
}
