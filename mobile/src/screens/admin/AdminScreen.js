import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Modal,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { getUsers, updateUserRole, suspendUser, getSystemStats, getUserReportsAdmin, deleteReport } from '../../config/api';
import { useAuth } from '../../context/AuthContext';

const ROLE_COLORS = { citizen: '#1565c0', municipal: '#e65100', admin: '#6a1b9a' };

export default function AdminScreen() {
  const { signOut } = useAuth();
  const [tab,    setTab]    = useState('users');  // 'users' | 'system'
  const [users,  setUsers]  = useState([]);
  const [stats,  setStats]  = useState(null);
  const [loading, setLoading] = useState(true);
  const [search,  setSearch]  = useState('');
  const [selected, setSelected] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [showReportsModal, setShowReportsModal] = useState(false);
  const [userReports, setUserReports] = useState([]);
  const [reportsLoading, setReportsLoading] = useState(false);

  const load = async () => {
    try {
      if (tab === 'users') {
        const data = await getUsers();
        setUsers(data.users || []);
      } else {
        const data = await getSystemStats();
        setStats(data);
      }
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [tab]));

  const handleRoleChange = async (uid, role) => {
    try {
      await updateUserRole(uid, role);
      setShowModal(false);
      load();
    } catch (e) {
      Alert.alert('Update failed', e.response?.data?.detail || e.message);
    }
  };

  const handleSuspend = (user) => {
    const action = user.is_active ? 'suspend' : 're-activate';
    Alert.alert(`${action.charAt(0).toUpperCase() + action.slice(1)} User`,
      `Are you sure you want to ${action} ${user.display_name || user.uid}?`,
      [{ text: 'Cancel' }, {
        text: action.charAt(0).toUpperCase() + action.slice(1),
        style: 'destructive',
        onPress: async () => {
          await suspendUser(user.uid, user.is_active);
          load();
        }
      }]
    );
  };

  const fetchUserReports = async (uid) => {
    setReportsLoading(true);
    try {
      const data = await getUserReportsAdmin(uid);
      setUserReports(data.reports || []);
    } catch (e) {
      Alert.alert('Error', 'Failed to fetch user reports: ' + e.message);
    } finally {
      setReportsLoading(false);
    }
  };

  const handleDeleteReport = (reportId) => {
    Alert.alert('Delete Report', 'Permanently delete this report?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        try {
          await deleteReport(reportId);
          Alert.alert('Deleted', 'Report has been permanently deleted.');
          fetchUserReports(selected.uid); // Refresh the list
          load(); // Refresh user stats on main list
        } catch (e) {
          Alert.alert('Error', 'Failed to delete report: ' + e.message);
        }
      }}
    ]);
  };

  const filtered = users.filter(u =>
    !search || (u.display_name || '').toLowerCase().includes(search.toLowerCase())
      || (u.email || '').toLowerCase().includes(search.toLowerCase())
  );

  const renderUser = ({ item: u }) => (
    <TouchableOpacity style={s.userCard} onPress={() => { setSelected(u); setShowModal(true); }}>
      <View style={[s.avatar, { backgroundColor: ROLE_COLORS[u.role] + '22' }]}>
        <Text style={[s.avatarT, { color: ROLE_COLORS[u.role] }]}>
          {(u.display_name || u.email || 'U')[0].toUpperCase()}
        </Text>
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={s.userName}>{u.display_name || 'No name'}</Text>
        <Text style={s.userEmail}>{u.email || u.phone || u.uid?.slice(0, 12)}</Text>
        <View style={s.userMeta}>
          <View style={[s.roleBadge, { backgroundColor: ROLE_COLORS[u.role] + '22' }]}>
            <Text style={[s.roleBadgeT, { color: ROLE_COLORS[u.role] }]}>{u.role}</Text>
          </View>
          <Text style={s.userStats}>{u.total_reports || 0} reports • {u.total_tokens || 0} tokens</Text>
        </View>
      </View>
      {!u.is_active && (
        <View style={s.suspendedBadge}>
          <Text style={s.suspendedT}>SUSPENDED</Text>
        </View>
      )}
      <Ionicons name="chevron-forward" size={16} color="#bdbdbd" />
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.headerTitle}>Admin Panel</Text>
          <Text style={s.headerSub}>System Management</Text>
        </View>
        <TouchableOpacity onPress={signOut}>
          <Ionicons name="log-out-outline" size={24} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={s.tabRow}>
        {['users', 'system'].map(t => (
          <TouchableOpacity key={t} style={[s.tab, tab === t && s.tabActive]} onPress={() => setTab(t)}>
            <Ionicons name={t === 'users' ? 'people' : 'hardware-chip'} size={16}
              color={tab === t ? '#fff' : '#9e9e9e'} />
            <Text style={[s.tabT, tab === t && s.tabTA]}>{t.charAt(0).toUpperCase() + t.slice(1)}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator size="large" color="#6a1b9a" />
        </View>
      ) : tab === 'users' ? (
        <>
          {/* Search */}
          <View style={s.searchRow}>
            <Ionicons name="search" size={18} color="#9e9e9e" />
            <TextInput style={s.searchInput} placeholder="Search users…"
              value={search} onChangeText={setSearch} />
          </View>
          <Text style={s.countT}>{filtered.length} users</Text>
          <FlatList data={filtered} keyExtractor={i => i.uid} renderItem={renderUser}
            contentContainerStyle={{ padding: 12 }} />
        </>
      ) : (
        // System stats
        <View style={{ padding: 16 }}>
          {stats && (<>
            <SystemRow label="Status"         value={stats.status}           good />
            <SystemRow label="Total Reports"  value={String(stats.total_reports)} />
            <SystemRow label="Total Users"    value={String(stats.total_users)} />
            <SystemRow label="GPU"            value={stats.gpu_name} />
            <SystemRow label="CUDA"           value={stats.cuda_available ? 'Yes ✅' : 'No (CPU)'} />
            <SystemRow label="Python"         value={stats.python_version} />
            <SystemRow label="Storage"        value={stats.storage_mode} />
            <SystemRow label="Model"          value={stats.model_path?.split('/').pop()} />
          </>)}
        </View>
      )}

      {/* User management modal */}
      <Modal visible={showModal} transparent animationType="slide"
        onRequestClose={() => setShowModal(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            {selected && (<>
              <Text style={s.modalTitle}>{selected.display_name || 'User'}</Text>
              <Text style={s.modalSub}>{selected.email || selected.uid}</Text>

              <Text style={[s.sectionLbl, { marginTop: 16 }]}>Change Role</Text>
              {['citizen', 'municipal', 'admin'].map(role => (
                <TouchableOpacity key={role} style={s.roleOpt}
                  onPress={() => handleRoleChange(selected.uid, role)}>
                  <View style={[s.roleDot, { backgroundColor: ROLE_COLORS[role] }]} />
                  <Text style={s.roleOptT}>{role.charAt(0).toUpperCase() + role.slice(1)}</Text>
                  {selected.role === role && <Ionicons name="checkmark" size={18} color={ROLE_COLORS[role]} />}
                </TouchableOpacity>
              ))}

              <TouchableOpacity style={[s.suspendBtn, { backgroundColor: selected.is_active ? '#c62828' : '#2e7d32' }]}
                onPress={() => { setShowModal(false); handleSuspend(selected); }}>
                <Ionicons name={selected.is_active ? 'ban' : 'checkmark-circle'} size={18} color="#fff" />
                <Text style={s.suspendBtnT}>{selected.is_active ? 'Suspend Account' : 'Re-activate Account'}</Text>
              </TouchableOpacity>

              <TouchableOpacity style={[s.suspendBtn, { backgroundColor: '#1565c0', marginTop: 12 }]}
                onPress={() => {
                  setShowModal(false);
                  setShowReportsModal(true);
                  fetchUserReports(selected.uid);
                }}>
                <Ionicons name="document-text" size={18} color="#fff" />
                <Text style={s.suspendBtnT}>View User's Reports</Text>
              </TouchableOpacity>

              <TouchableOpacity style={s.cancelBtn} onPress={() => setShowModal(false)}>
                <Text style={s.cancelBtnT}>Cancel</Text>
              </TouchableOpacity>
            </>)}
          </View>
        </View>
      </Modal>

      {/* User Reports Modal */}
      <Modal visible={showReportsModal} transparent animationType="slide" onRequestClose={() => setShowReportsModal(false)}>
        <View style={s.modalOverlay}>
          <View style={[s.modalSheet, { height: '85%' }]}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <Text style={s.modalTitle}>{selected?.display_name}'s Reports</Text>
              <TouchableOpacity onPress={() => setShowReportsModal(false)}>
                <Ionicons name="close" size={24} color="#212121" />
              </TouchableOpacity>
            </View>
            
            {reportsLoading ? (
              <ActivityIndicator size="large" color="#6a1b9a" style={{ marginTop: 20 }} />
            ) : userReports.length === 0 ? (
              <Text style={{ textAlign: 'center', color: '#9e9e9e', marginTop: 20 }}>No reports found for this user.</Text>
            ) : (
              <FlatList 
                data={userReports} 
                keyExtractor={item => item.id}
                showsVerticalScrollIndicator={false}
                renderItem={({ item }) => (
                  <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 14, borderBottomWidth: 1, borderColor: '#f0f0f0' }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: '700', color: '#212121', fontSize: 15 }}>
                        {item.inference?.primary_class?.replace('_', ' ') || 'Unknown Detection'}
                      </Text>
                      <Text style={{ fontSize: 13, color: '#757575', marginTop: 4 }}>
                        Status: <Text style={{ fontWeight: '600' }}>{item.status.toUpperCase()}</Text> • Score: {Math.round(item.priority_score || 0)}
                      </Text>
                      <Text style={{ fontSize: 11, color: '#9e9e9e', marginTop: 4 }}>
                        {new Date(item.created_at).toLocaleString()}
                      </Text>
                    </View>
                    <TouchableOpacity 
                      style={{ padding: 10, backgroundColor: '#ffebee', borderRadius: 10, marginLeft: 10 }}
                      onPress={() => handleDeleteReport(item.id)}
                    >
                      <Ionicons name="trash" size={20} color="#d32f2f" />
                    </TouchableOpacity>
                  </View>
                )}
              />
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function SystemRow({ label, value, good }) {
  return (
    <View style={s.sysRow}>
      <Text style={s.sysLabel}>{label}</Text>
      <Text style={[s.sysValue, good && { color: '#2e7d32' }]}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe:        { flex: 1, backgroundColor: '#f5f5f5' },
  header:      { backgroundColor: '#6a1b9a', padding: 20, flexDirection: 'row',
                 justifyContent: 'space-between', alignItems: 'center' },
  headerTitle: { color: '#fff', fontSize: 20, fontWeight: '800' },
  headerSub:   { color: '#e1bee7', fontSize: 12 },
  tabRow:      { flexDirection: 'row', backgroundColor: '#fff', padding: 8, gap: 8 },
  tab:         { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                 gap: 6, paddingVertical: 10, borderRadius: 10 },
  tabActive:   { backgroundColor: '#6a1b9a' },
  tabT:        { fontSize: 13, color: '#9e9e9e', fontWeight: '600' },
  tabTA:       { color: '#fff' },
  searchRow:   { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff',
                 margin: 12, borderRadius: 10, padding: 12, gap: 10, borderWidth: 1, borderColor: '#e0e0e0' },
  searchInput: { flex: 1, fontSize: 14 },
  countT:      { fontSize: 12, color: '#9e9e9e', marginLeft: 14, marginBottom: 4 },
  userCard:    { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 12,
                 marginBottom: 8, padding: 14, shadowColor: '#000', shadowOpacity: 0.05, elevation: 1 },
  avatar:      { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center' },
  avatarT:     { fontSize: 20, fontWeight: '800' },
  userName:    { fontWeight: '700', color: '#212121', fontSize: 14 },
  userEmail:   { color: '#9e9e9e', fontSize: 12, marginTop: 2 },
  userMeta:    { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 5 },
  roleBadge:   { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12 },
  roleBadgeT:  { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  userStats:   { fontSize: 11, color: '#bdbdbd' },
  suspendedBadge: { backgroundColor: '#b71c1c', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, marginRight: 8 },
  suspendedT:  { color: '#fff', fontSize: 9, fontWeight: '800' },
  sysRow:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                 backgroundColor: '#fff', borderRadius: 10, padding: 14, marginBottom: 8 },
  sysLabel:    { color: '#616161', fontSize: 13 },
  sysValue:    { fontWeight: '700', color: '#212121', fontSize: 13 },
  sectionLbl:  { fontSize: 12, color: '#9e9e9e', fontWeight: '600', marginBottom: 8 },
  modalOverlay:{ flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet:  { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
                 padding: 24, paddingBottom: 44 },
  modalTitle:  { fontSize: 18, fontWeight: '800', color: '#212121' },
  modalSub:    { fontSize: 12, color: '#9e9e9e', marginTop: 2 },
  roleOpt:     { flexDirection: 'row', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderColor: '#f5f5f5', gap: 14 },
  roleDot:     { width: 12, height: 12, borderRadius: 6 },
  roleOptT:    { fontSize: 15, color: '#212121', flex: 1 },
  suspendBtn:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                 borderRadius: 10, padding: 14, gap: 8, marginTop: 16 },
  suspendBtnT: { color: '#fff', fontWeight: '700', fontSize: 15 },
  cancelBtn:   { alignItems: 'center', padding: 14, marginTop: 8 },
  cancelBtnT:  { color: '#9e9e9e', fontSize: 14 },
});
