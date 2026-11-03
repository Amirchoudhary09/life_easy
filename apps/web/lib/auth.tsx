"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, isSignedIn, onAuthChange, refreshSession } from "./api";
import type { User } from "./types";

interface AuthState {
  ready: boolean;
  user: User | null;
  reloadUser: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  const reloadUser = useCallback(async () => {
    if (!isSignedIn()) {
      setUser(null);
      return;
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (!isSignedIn()) await refreshSession();
      if (alive) {
        await reloadUser();
        setReady(true);
      }
    })();
    const off = onAuthChange((signedIn) => {
      if (!signedIn) setUser(null);
    });
    return () => {
      alive = false;
      off();
    };
  }, [reloadUser]);

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ ready, user, reloadUser, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
