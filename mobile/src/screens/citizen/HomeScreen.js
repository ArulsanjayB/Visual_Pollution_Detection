import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../../context/AuthContext';
import { getMyReports, absoluteUrl } from '../../config/api';
import { format } from 'date-fns';

const SEVERITY_COLORS = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' };
const STATUS_COLORS   = { pending: '#1565c0', in_progress: '#e65100', completed: '#2e7d32', rejected: '#b71c1c' };
const CLASS_ICONS     = { Potholes: 'alert-circle', Abandoned_Vehicles: 'car', Construction_Debris: 'construct' };

export default function CitizenHomeScreen({ navigation }) {
  const { profile, signOut } = useAuth();
  const [reports, setReports]     = useState([]);
  const [stats, setStats]         = useState({ pending: 0, in_progress: 0, completed: 0 });
  const [loading, setLoading]     = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadData = async () => {
    try {
      const data = await getMyReports(1, 10);
      setReports(data.reports || []);
      const st = { pending: 0, in_progress: 0, completed: 0 };
      (data.reports || []).forEach(r => { if (st[r.status] !== undefined) st[r.status]++; });
      setStats(st);
    } catch (e) {
      console.warn('Failed to load home data:', e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useFocusEffect(useCallback(() => { loadData(); }, []));

  const onRefresh = () => { setRefreshing(true); loadData(); };

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>

        {/* Header with logout button */}
        <View style={s.header}>
          <View style={{ flex: 1 }}>
            <Text style={s.greeting}>Hello, {profile?.display_name?.split(' ')[0] || 'Citizen'} 👋</Text>
            <Text style={s.subGreet}>Help keep your city clean</Text>
          </View>
          <View style={s.tokenBadge}>
            <Ionicons name="star" size={16} color="#ffd600" />
            <Text style={s.tokenText}>{profile?.total_tokens || 0}</Text>
          </View>
          <TouchableOpacity onPress={signOut} style={s.logoutBtn} accessibilityLabel="Sign out">
            <Ionicons name="log-out-outline" size={24} color="#fff" />
          </TouchableOpacity>
        </View>

        {/* Quick Action */}
        <TouchableOpacity style={s.reportButton} onPress={() => navigation.navigate('Report')}>
          <Ionicons name="camera" size={24} color="#fff" />
          <Text style={s.reportButtonText}>Report Pollution</Text>
          <Ionicons name="arrow-forward" size={20} color="#fff" />
        </TouchableOpacity>

        {/* Stats cards */}
        <Text style={s.sectionTitle}>My Reports</Text>
        <View style={s.statsRow}>
          <StatCard label="Pending"     count={stats.pending}     color="#1565c0" icon="time" />
          <StatCard label="In Progress" count={stats.in_progress} color="#e65100" icon="construct" />
          <StatCard label="Resolved"    count={stats.completed}   color="#2e7d32" icon="checkmark-circle" />
        </View>

        {/* Reward card */}
        <View style={s.rewardCard}>
          <Ionicons name="trophy" size={36} color="#ffd600" />
          <View style={{ flex: 1, marginLeft: 14 }}>
            <Text style={s.rewardTitle}>Reward Tokens</Text>
            <Text style={s.rewardSub}>Earn 10 tokens per resolved report</Text>
          </View>
          <Text style={s.rewardCount}>{profile?.total_tokens || 0}</Text>
        </View>

        {/* Recent reports */}
        <View style={s.sectionHeader}>
          <Text style={s.sectionTitle}>Recent Reports</Text>
          <TouchableOpacity onPress={() => navigation.navigate('History')}>
            <Text style={s.seeAllText}>See All</Text>
          </TouchableOpacity>
        </View>

        {reports.length === 0 && !loading ? (
          <View style={s.emptyState}>
            <Ionicons name="camera-outline" size={60} color="#bdbdbd" />
            <Text style={s.emptyText}>No reports yet</Text>
            <Text style={s.emptySub}>Tap "Report Pollution" to submit your first report</Text>
          </View>
        ) : (
          reports.map(r => (
            <ReportCard
              key={r.id}
              report={r}
              onPress={() => navigation.navigate('ReportDetail', { reportId: r.id })}
            />
          ))
        )}

      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({ label, count, color, icon }) {
  return (
    <View style={[s.statCard, { borderTopColor: color }]}>
      <Ionicons name={icon} size={22} color={color} />
      <Text style={[s.statCount, { color }]}>{count}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function ReportCard({ report, onPress }) {
  const sev = SEVERITY_COLORS[report.inference?.severity] || '#757575';
  const status = STATUS_COLORS[report.status] || '#9e9e9e';
  const processing = report.inference?.processing;
  return (
    <TouchableOpacity style={s.reportCard} onPress={onPress}>
      <View style={[s.classIcon, { backgroundColor: sev + '20' }]}>
        {processing ? (
          <Ionicons name="sync" size={22} color="#1a237e" />
        ) : (
          <Ionicons
            name={CLASS_ICONS[report.inference?.primary_class] || 'alert'}
            size={22}
            color={sev}
          />
        )}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.reportTitle}>
          {processing
            ? 'Analyzing…'
            : (report.inference?.primary_class || 'unknown').replace(/_/g, ' ')}
        </Text>
        <Text style={s.reportSub}>
          {format(new Date(report.created_at), 'PPp')} • {report.location?.address || 'Location recorded'}
        </Text>
        <View style={{ flexDirection: 'row', marginTop: 6 }}>
          {!processing && (
            <View style={[s.tag, { backgroundColor: sev + '20' }]}>
              <Text style={[s.tagText, { color: sev }]}>{report.inference?.severity || 'N/A'}</Text>
            </View>
          )}
          <View style={[s.tag, {
            backgroundColor: status + '20',
            marginLeft: processing ? 0 : 6,
          }]}>
            <Text style={[s.tagText, { color: status }]}>
              {processing ? 'processing' : (report.status || '').replace('_', ' ')}
            </Text>
          </View>
        </View>
      </View>
      <Ionicons name="chevron-forward" size={22} color="#bdbdbd" />
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: '#f5f5f5' },
  header:    { flexDirection: 'row', alignItems: 'center',
                paddingHorizontal: 20, paddingTop: 20, paddingBottom: 20,
                backgroundColor: '#1a237e' },
  greeting:  { fontSize: 22, fontWeight: 'bold', color: '#fff' },
  subGreet:  { fontSize: 13, color: '#c5cae9', marginTop: 2 },
  tokenBadge:{ flexDirection: 'row', alignItems: 'center', backgroundColor: '#ffffff25',
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 },
  tokenText: { color: '#fff', fontWeight: 'bold', marginLeft: 6, fontSize: 14 },
  logoutBtn: { marginLeft: 12, padding: 6 },
  reportButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  backgroundColor: '#d32f2f', marginHorizontal: 20, marginTop: 20,
                  padding: 16, borderRadius: 12, elevation: 3 },
  reportButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold', flex: 1, textAlign: 'center' },
  sectionTitle: { fontSize: 16, fontWeight: 'bold', marginTop: 24, marginHorizontal: 20, color: '#212121' },
  statsRow:     { flexDirection: 'row', justifyContent: 'space-between',
                  marginHorizontal: 20, marginTop: 12 },
  statCard:     { flex: 1, backgroundColor: '#fff', marginHorizontal: 3,
                  borderTopWidth: 3, borderRadius: 10, padding: 14,
                  alignItems: 'center', elevation: 1 },
  statCount:    { fontSize: 28, fontWeight: 'bold', marginTop: 4 },
  statLabel:    { fontSize: 11, color: '#757575', marginTop: 2 },
  rewardCard:   { flexDirection: 'row', alignItems: 'center',
                  backgroundColor: '#fff8e1', marginHorizontal: 20, marginTop: 14,
                  borderRadius: 10, padding: 14, borderLeftWidth: 4, borderLeftColor: '#ffb300' },
  rewardTitle:  { fontSize: 15, fontWeight: 'bold', color: '#e65100' },
  rewardSub:    { fontSize: 12, color: '#8d6e63', marginTop: 2 },
  rewardCount:  { fontSize: 28, fontWeight: 'bold', color: '#e65100' },
  sectionHeader:{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                  marginTop: 24, marginHorizontal: 20 },
  seeAllText:   { color: '#1a237e', fontSize: 13, fontWeight: 'bold', marginTop: 24 },
  emptyState:   { alignItems: 'center', paddingVertical: 40 },
  emptyText:    { marginTop: 10, fontSize: 16, color: '#9e9e9e' },
  emptySub:     { marginTop: 4, fontSize: 12, color: '#bdbdbd', textAlign: 'center' },
  reportCard:   { flexDirection: 'row', alignItems: 'center',
                  backgroundColor: '#fff', marginHorizontal: 20, marginTop: 10,
                  borderRadius: 10, padding: 12, elevation: 1 },
  classIcon:    { width: 42, height: 42, borderRadius: 21,
                  justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  reportTitle:  { fontSize: 15, fontWeight: 'bold', color: '#212121' },
  reportSub:    { fontSize: 12, color: '#757575', marginTop: 2 },
  tag:          { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  tagText:      { fontSize: 10, fontWeight: 'bold', textTransform: 'uppercase' },
});
