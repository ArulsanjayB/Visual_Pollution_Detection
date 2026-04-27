/**
 * Dev-mode auth — no Firebase. Stores uid in AsyncStorage, sends as X-Dev-User
 * header so the FastAPI backend (DATABASE_MODE=local) auto-auths the user.
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { registerUser, getMyProfile, setDevUser } from '../config/api';

const AuthContext = createContext(null);
const STORAGE_KEY = 'civiclens_user';

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEY);
        if (saved) {
          const u = JSON.parse(saved);
          setDevUser(u.uid);
          setUser(u);
          try {
            const p = await getMyProfile();
            setProfile(p);
          } catch {}
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const signIn = async ({ uid, displayName = '', role = 'citizen' }) => {
    if (!uid) throw new Error('UID is required');
    const u = { uid, displayName: displayName || uid, role };
    setDevUser(uid);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(u));
    setUser(u);
    try { await registerUser('dev:' + uid, displayName, ''); } catch {}
    try {
      const p = await getMyProfile();
      setProfile(p);
    } catch {
      setProfile({ uid, display_name: displayName, role });
    }
    return u;
  };

  const signOut = async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setDevUser(null);
    setUser(null);
    setProfile(null);
  };

  const refreshProfile = async () => {
    try {
      const p = await getMyProfile();
      setProfile(p);
      return p;
    } catch { return null; }
  };

  return (
    <AuthContext.Provider value={{
      user, profile, loading,
      role: profile?.role || user?.role || 'citizen',
      signIn, signOut, refreshProfile,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
