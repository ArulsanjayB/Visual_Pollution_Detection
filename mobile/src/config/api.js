/**
 * Backend API client.
 * Dev-mode auth via X-Dev-User header (no Firebase).
 * Auto-detects the backend URL from Expo's host (no manual IP config needed).
 */
import axios from 'axios';
import Constants from 'expo-constants';
import { Platform } from 'react-native';

// ── Resolve backend URL (auto-detect Expo host) ─────────────────────────────
// When you run `npx expo start`, Expo Go receives this app's bundle from your
// PC's LAN IP. We extract that IP from Constants.expoConfig.hostUri and
// assume the backend runs on port 8000 on the same PC.
//
// Resolution priority:
//   1. Explicit override in app.json > extra > apiBaseUrl (if a real URL)
//   2. EXPO_PUBLIC_API_BASE_URL env var
//   3. AUTO-DETECT from Expo hostUri
//   4. Platform fallback
function resolveBaseUrl() {
  // 1. Explicit override
  const extra = Constants.expoConfig?.extra?.apiBaseUrl;
  if (extra && extra !== 'auto' && extra !== 'http://10.0.2.2:8000') {
    return extra;
  }

  // 2. Env var
  if (process.env.EXPO_PUBLIC_API_BASE_URL) {
    return process.env.EXPO_PUBLIC_API_BASE_URL;
  }

  // 3. AUTO: SDK 54 exposes host under expoConfig.hostUri (LAN mode) OR
  //    as part of the direct URL (tunnel mode). In tunnel mode we can't
  //    reach the backend unless it's also tunneled, so fall back to LAN IP.
  const hostUri = Constants.expoConfig?.hostUri || Constants.expoGoConfig?.hostUri;
  if (hostUri) {
    const host = hostUri.split(':')[0].split('/')[0];
    // Skip tunnel hosts (they end in .exp.direct) — backend lives on LAN
    if (host && host !== 'localhost' && !host.endsWith('.exp.direct')) {
      return `http://${host}:8000`;
    }
  }

  // 4. Platform fallback
  if (Platform.OS === 'android') return 'http://10.0.2.2:8000';  // Android emulator
  return 'http://localhost:8000';                                  // iOS sim / web
}

export const BASE_URL = resolveBaseUrl();
console.log('[API] Backend base URL:', BASE_URL);

const api = axios.create({ baseURL: BASE_URL, timeout: 180000 });

let currentDevUser = null;
export const setDevUser = (uid) => { currentDevUser = uid; };

api.interceptors.request.use((config) => {
  if (currentDevUser) config.headers['X-Dev-User'] = currentDevUser;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message;
    console.warn(`API ${err.config?.method?.toUpperCase()} ${err.config?.url}:`, msg);
    return Promise.reject(err);
  }
);

// ── Auth ───────────────────────────────────────────────────────────────────
export const registerUser = async (idToken, displayName, phone) => {
  const { data } = await api.post('/api/auth/register', {
    id_token: idToken, display_name: displayName, phone,
  });
  return data;
};
export const getMyProfile = async () => (await api.get('/api/auth/me')).data;
export const updateProfile = async (updates) => (await api.patch('/api/auth/me', updates)).data;

// ── Reports (Citizen) ──────────────────────────────────────────────────────
export const submitReport = async (imageUri, location, description = '', xaiMode = 'gradcam', onProgress) => {
  const formData = new FormData();
  formData.append('image', {
    uri: imageUri, type: 'image/jpeg', name: `report_${Date.now()}.jpg`,
  });
  formData.append('latitude',        String(location.latitude));
  formData.append('longitude',       String(location.longitude));
  formData.append('address',         location.address || '');
  formData.append('location_source', location.source || 'gps');
  formData.append('description',     description);
  formData.append('xai_mode',        xaiMode);

  const { data } = await api.post('/api/reports/submit', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => { if (onProgress) onProgress(Math.round((e.loaded * 100) / e.total)); },
  });
  return data;
};
export const getMyReports = async (page = 1, pageSize = 10) =>
  (await api.get('/api/reports/my', { params: { page, page_size: pageSize } })).data;
export const getReport = async (reportId) => (await api.get(`/api/reports/${reportId}`)).data;
export const requestXAI = async (reportId, method = 'zoolime') =>
  (await api.post(`/api/reports/${reportId}/xai`, null, { params: { method } })).data;

// ── Municipal ──────────────────────────────────────────────────────────────
export const getMunicipalReports = async (params = {}) =>
  (await api.get('/api/municipal/reports', { params })).data;
export const getMunicipalReport = async (reportId) =>
  (await api.get(`/api/municipal/reports/${reportId}`)).data;
export const updateReportStatus = async (reportId, updates) =>
  (await api.patch(`/api/municipal/reports/${reportId}`, updates)).data;
export const getDashboardStats = async () => (await api.get('/api/municipal/stats')).data;
export const getHeatmapData = async () => (await api.get('/api/municipal/heatmap')).data;

// ── Admin ──────────────────────────────────────────────────────────────────
export const getUsers = async (params = {}) => (await api.get('/api/admin/users', { params })).data;
export const updateUserRole = async (uid, role) =>
  (await api.patch(`/api/admin/users/${uid}/role`, { role })).data;
export const suspendUser = async (uid, suspend = true) =>
  (await api.patch(`/api/admin/users/${uid}/suspend`, null, { params: { suspend } })).data;
export const deleteReport = async (reportId) => (await api.delete(`/api/admin/reports/${reportId}`)).data;
export const getUserReportsAdmin = async (uid) => (await api.get(`/api/admin/users/${uid}/reports`)).data;
export const deleteAllUserReports = async (uid) => (await api.delete(`/api/admin/users/${uid}/reports`)).data;
export const getSystemStats = async () => (await api.get('/api/admin/system')).data;

export const absoluteUrl = (path) => {
  if (!path) return null;
  if (path.startsWith('http')) return path;
  return `${BASE_URL}${path}`;
};

export default api;
