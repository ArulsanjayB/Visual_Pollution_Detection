import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../context/AuthContext';

const ROLES = [
  { key: 'citizen',   label: 'Citizen',   desc: 'Report pollution',        icon: 'person',           color: '#1a237e' },
  { key: 'municipal', label: 'Municipal', desc: 'Review & resolve reports', icon: 'business',         color: '#2e7d32' },
  { key: 'admin',     label: 'Admin',     desc: 'Manage users & system',   icon: 'shield-checkmark', color: '#c62828' },
];

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [uid,         setUid]         = useState('');
  const [displayName, setDisplayName] = useState('');
  const [role,        setRole]        = useState('citizen');
  const [loading,     setLoading]     = useState(false);

  const handleSignIn = async () => {
    const trimmed = uid.trim().replace(/\s+/g, '_').toLowerCase();
    if (!trimmed) {
      Alert.alert('User ID required', 'Please enter a username (e.g., "alice").');
      return;
    }
    setLoading(true);
    try {
      await signIn({ uid: trimmed, displayName: displayName.trim() || trimmed, role });
    } catch (e) {
      Alert.alert('Sign-in failed', e.message);
    } finally {
      setLoading(false);
    }
  };

  const quick = (u, n, r) => { setUid(u); setDisplayName(n); setRole(r); };

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={s.header}>
          <View style={s.iconBox}><Ionicons name="scan" size={48} color="#fff" /></View>
          <Text style={s.title}>CivicLens</Text>
          <Text style={s.subtitle}>AI-Powered Visual Pollution Reporter</Text>
          <View style={s.devPill}>
            <Ionicons name="construct" size={12} color="#f57f17" />
            <Text style={s.devText}>DEV MODE</Text>
          </View>
        </View>

        <View style={s.card}>
          <Text style={s.cardTitle}>Sign In</Text>

          <Text style={s.label}>Username</Text>
          <View style={s.inputRow}>
            <Ionicons name="person-outline" size={18} color="#9e9e9e" style={{ marginRight: 8 }} />
            <TextInput style={s.input} placeholder="e.g., alice" value={uid} onChangeText={setUid}
                       autoCapitalize="none" autoCorrect={false} />
          </View>

          <Text style={s.label}>Display Name (optional)</Text>
          <View style={s.inputRow}>
            <Ionicons name="text-outline" size={18} color="#9e9e9e" style={{ marginRight: 8 }} />
            <TextInput style={s.input} placeholder="e.g., Alice Johnson" value={displayName}
                       onChangeText={setDisplayName} />
          </View>

          <Text style={s.label}>Role</Text>
          <View style={{ gap: 8 }}>
            {ROLES.map(r => (
              <TouchableOpacity key={r.key}
                style={[s.roleBtn, role === r.key && { borderColor: r.color, backgroundColor: `${r.color}10` }]}
                onPress={() => setRole(r.key)}>
                <View style={[s.roleIcon, { backgroundColor: r.color }]}>
                  <Ionicons name={r.icon} size={18} color="#fff" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.roleLabel, role === r.key && { color: r.color }]}>{r.label}</Text>
                  <Text style={s.roleDesc}>{r.desc}</Text>
                </View>
                {role === r.key && <Ionicons name="checkmark-circle" size={20} color={r.color} />}
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity style={s.primaryBtn} onPress={handleSignIn} disabled={loading}>
            {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnText}>Sign In</Text>}
          </TouchableOpacity>
        </View>

        <View style={s.presetCard}>
          <Text style={s.presetTitle}>Quick Sign-In (for demo)</Text>
          <View style={s.presetRow}>
            <TouchableOpacity style={s.presetBtn}
              onPress={() => quick('dev_citizen', 'Test Citizen', 'citizen')}>
              <Ionicons name="person" size={16} color="#1a237e" />
              <Text style={s.presetText}>Citizen</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.presetBtn}
              onPress={() => quick('dev_municipal', 'Municipal Officer', 'municipal')}>
              <Ionicons name="business" size={16} color="#2e7d32" />
              <Text style={s.presetText}>Municipal</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.presetBtn}
              onPress={() => quick('dev_admin', 'Dev Admin', 'admin')}>
              <Ionicons name="shield-checkmark" size={16} color="#c62828" />
              <Text style={s.presetText}>Admin</Text>
            </TouchableOpacity>
          </View>
        </View>

        <Text style={s.footer}>
          Dev mode: no password required. Authenticates via X-Dev-User header.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:     { flex: 1, backgroundColor: '#f5f5f5' },
  scroll:   { flexGrow: 1, padding: 20, paddingBottom: 40 },
  header:   { alignItems: 'center', paddingVertical: 28 },
  iconBox:  { backgroundColor: '#1a237e', padding: 20, borderRadius: 24, marginBottom: 14 },
  title:    { fontSize: 30, fontWeight: '800', color: '#1a237e' },
  subtitle: { fontSize: 13, color: '#616161', marginTop: 4 },
  devPill:  { flexDirection: 'row', alignItems: 'center', gap: 4,
              backgroundColor: '#fff3e0', paddingHorizontal: 10, paddingVertical: 4,
              borderRadius: 12, marginTop: 10, borderWidth: 1, borderColor: '#ffcc80' },
  devText:  { color: '#f57f17', fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },

  card:      { backgroundColor: '#fff', borderRadius: 16, padding: 20,
               shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 12,
               elevation: 4, marginBottom: 16 },
  cardTitle: { fontSize: 18, fontWeight: '700', color: '#212121', marginBottom: 16 },

  label:    { fontSize: 12, color: '#616161', marginBottom: 6, marginTop: 12, fontWeight: '600' },
  inputRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 1.5,
              borderColor: '#e0e0e0', borderRadius: 10, paddingHorizontal: 12,
              paddingVertical: 10, backgroundColor: '#fafafa' },
  input:    { flex: 1, fontSize: 14, color: '#212121' },

  roleBtn:  { flexDirection: 'row', alignItems: 'center', borderWidth: 1.5,
              borderColor: '#e0e0e0', borderRadius: 10, padding: 10, gap: 10, backgroundColor: '#fafafa' },
  roleIcon: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  roleLabel:{ fontWeight: '700', color: '#212121', fontSize: 13 },
  roleDesc: { color: '#9e9e9e', fontSize: 11, marginTop: 1 },

  primaryBtn:     { backgroundColor: '#1a237e', borderRadius: 10, padding: 14,
                    alignItems: 'center', marginTop: 20 },
  primaryBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },

  presetCard: { backgroundColor: '#fff', borderRadius: 12, padding: 14, marginBottom: 12 },
  presetTitle:{ fontSize: 12, color: '#9e9e9e', marginBottom: 8, fontWeight: '600' },
  presetRow:  { flexDirection: 'row', gap: 8 },
  presetBtn:  { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                gap: 4, borderWidth: 1, borderColor: '#e0e0e0', borderRadius: 8, padding: 8 },
  presetText: { fontSize: 11, fontWeight: '600', color: '#616161' },

  footer: { textAlign: 'center', fontSize: 11, color: '#9e9e9e', lineHeight: 16, paddingHorizontal: 10 },
});
