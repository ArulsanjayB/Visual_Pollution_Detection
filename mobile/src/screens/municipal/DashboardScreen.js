import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { getMunicipalReports, getDashboardStats, updateReportStatus, absoluteUrl } from '../../config/api';
import { useAuth } from '../../context/AuthContext';
import { format } from 'date-fns';

const SEV_CLR  = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' };
const STAT_CLR = { pending: '#1565c0', in_progress: '#e65100', completed: '#2e7d32', rejected: '#9e9e9e' };
const NEXT_STATUS = { pending: 'in_progress', in_progress: 'completed' };

export default function MunicipalDashboard({ navigation }) {
  const { signOut } = useAuth();
  const [stats,      setStats]      = useState(null);
  const [reports,    setReports]    = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter,     setFilter]     = useState('pending');
  const [sortBy,     setSortBy]     = useState('priority_score');

  const load = async () => {
    try {
      const [s, r] = await Promise.all([
        getDashboardStats(),
        getMunicipalReports({ status: filter !== 'all' ? filter : undefined, sort_by: sortBy }),
      ]);
      setStats(s);
      setReports(r.reports || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [filter, sortBy]));

  const quickUpdate = async (reportId, status) => {
    try {
      await updateReportStatus(reportId, { status });
      load();
    } catch (e) {
      Alert.alert('Update failed', e.response?.data?.detail || e.message);
    }
  };

  const FILTERS = ['all', 'pending', 'in_progress', 'completed'];

  const renderReport = ({ item: r }) => {
    const sevClr  = SEV_CLR[r.severity] || '#757575';
    const statClr = STAT_CLR[r.status] || '#757575';
    const nextSt  = NEXT_STATUS[r.status];

    return (
      <View style={s.card}>
        <TouchableOpacity style={s.cardBody}
          onPress={() => navigation.navigate('MunicipalDetail', { reportId: r.id })}>
          <View style={[s.severityBar, { backgroundColor: sevClr }]} />
          <View style={{ flex: 1 }}>
            <View style={s.cardRow}>
              <Text style={s.cardClass}>{r.primary_class?.replace('_', ' ')}</Text>
              <View style={[s.badge, { backgroundColor: sevClr + '22' }]}>
                <Text style={[s.badgeT, { color: sevClr }]}>{r.severity}</Text>
              </View>
            </View>
            <Text style={s.cardAddr} numberOfLines={1}>
              📍 {r.location?.address || `${r.location?.latitude?.toFixed(4)}, ${r.location?.longitude?.toFixed(4)}`}
            </Text>
            <View style={s.cardRow}>
              <Text style={s.cardMeta}>Conf: {Math.round((r.confidence || 0) * 100)}%  •  Priority: {Math.round(r.priority_score || 0)}</Text>
              <View style={[s.badge, { backgroundColor: statClr + '22' }]}>
                <Text style={[s.badgeT, { color: statClr }]}>{r.status?.replace('_', ' ')}</Text>
              </View>
            </View>
          </View>
        </TouchableOpacity>

        {/* Quick action button */}
        {nextSt && (
          <TouchableOpacity style={[s.actionBtn, { backgroundColor: STAT_CLR[nextSt] }]}
            onPress={() => quickUpdate(r.id, nextSt)}>
            <Text style={s.actionBtnT}>{nextSt === 'in_progress' ? 'Start' : 'Resolve'}</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        <View>
          <Text style={s.headerTitle}>Municipal Dashboard</Text>
          <Text style={s.headerSub}>Visual Pollution Reports</Text>
        </View>
        <TouchableOpacity onPress={signOut}>
          <Ionicons name="log-out-outline" size={24} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Stats row */}
      {stats && (
        <View style={s.statsRow}>
          <StatCard label="Total"    value={stats.total_reports}              color="#1a237e" icon="documents" />
          <StatCard label="Pending"  value={stats.by_status?.pending || 0}   color="#1565c0" icon="time" />
          <StatCard label="Active"   value={stats.by_status?.in_progress||0} color="#e65100" icon="construct" />
          <StatCard label="Done"     value={stats.by_status?.completed || 0} color="#2e7d32" icon="checkmark-circle" />
        </View>
      )}

      {/* Sort + Filter */}
      <View style={s.controls}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {FILTERS.map(f => (
            <TouchableOpacity key={f} style={[s.fBtn, filter === f && s.fBtnA]} onPress={() => setFilter(f)}>
              <Text style={[s.fBtnT, filter === f && s.fBtnTA]}>{f.replace('_', ' ')}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <TouchableOpacity style={s.sortBtn}
          onPress={() => setSortBy(p => p === 'priority_score' ? 'created_at' : 'priority_score')}>
          <Ionicons name="swap-vertical" size={16} color="#1a237e" />
          <Text style={s.sortBtnT}>{sortBy === 'priority_score' ? 'Priority' : 'Latest'}</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator size="large" color="#1a237e" />
        </View>
      ) : (
        <FlatList
          data={reports}
          keyExtractor={i => i.id}
          renderItem={renderReport}
          contentContainerStyle={{ padding: 12 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
          ListEmptyComponent={
            <View style={{ alignItems: 'center', padding: 40 }}>
              <Ionicons name="checkmark-done-circle" size={48} color="#bdbdbd" />
              <Text style={{ color: '#9e9e9e', marginTop: 12 }}>No reports in this category</Text>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
}

function StatCard({ label, value, color, icon }) {
  return (
    <View style={[s.stat, { borderTopColor: color }]}>
      <Ionicons name={icon} size={18} color={color} />
      <Text style={[s.statVal, { color }]}>{value}</Text>
      <Text style={s.statLbl}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe:       { flex: 1, backgroundColor: '#f5f5f5' },
  header:     { backgroundColor: '#1a237e', padding: 20, flexDirection: 'row',
                justifyContent: 'space-between', alignItems: 'center' },
  headerTitle: { color: '#fff', fontSize: 20, fontWeight: '800' },
  headerSub:   { color: '#c5cae9', fontSize: 12, marginTop: 2 },
  statsRow:   { flexDirection: 'row', backgroundColor: '#fff', padding: 12, gap: 8 },
  stat:       { flex: 1, alignItems: 'center', borderTopWidth: 3, paddingTop: 10 },
  statVal:    { fontSize: 20, fontWeight: '900', marginVertical: 2 },
  statLbl:    { fontSize: 10, color: '#9e9e9e' },
  controls:   { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, backgroundColor: '#fff', borderBottomWidth: 1, borderColor: '#f0f0f0' },
  fBtn:       { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginRight: 8,
                backgroundColor: '#f5f5f5', borderWidth: 1, borderColor: '#e0e0e0' },
  fBtnA:      { backgroundColor: '#1a237e', borderColor: '#1a237e' },
  fBtnT:      { fontSize: 12, color: '#757575', textTransform: 'capitalize', fontWeight: '600' },
  fBtnTA:     { color: '#fff' },
  sortBtn:    { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10,
                paddingVertical: 6, backgroundColor: '#e8eaf6', borderRadius: 16, marginLeft: 8 },
  sortBtnT:   { fontSize: 11, color: '#1a237e', fontWeight: '700' },
  card:       { backgroundColor: '#fff', borderRadius: 12, marginBottom: 8, overflow: 'hidden',
                shadowColor: '#000', shadowOpacity: 0.06, elevation: 2 },
  cardBody:   { flexDirection: 'row', padding: 14, gap: 10 },
  severityBar: { width: 4, borderRadius: 2 },
  cardRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 },
  cardClass:  { fontWeight: '700', color: '#212121', fontSize: 14 },
  cardAddr:   { fontSize: 11, color: '#9e9e9e', marginVertical: 3 },
  cardMeta:   { fontSize: 11, color: '#757575' },
  badge:      { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12 },
  badgeT:     { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  actionBtn:  { padding: 10, alignItems: 'center' },
  actionBtnT: { color: '#fff', fontWeight: '700', fontSize: 13 },
});
