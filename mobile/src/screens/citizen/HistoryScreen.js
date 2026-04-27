import React, { useState, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { getMyReports, absoluteUrl } from '../../config/api';
import { format } from 'date-fns';

const SEV  = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' };
const STAT = { pending: '#1565c0', in_progress: '#e65100', completed: '#2e7d32', rejected: '#b71c1c' };

export default function HistoryScreen({ navigation }) {
  const [reports, setReports]   = useState([]);
  const [loading, setLoading]   = useState(true);
  const [page, setPage]         = useState(1);
  const [hasNext, setHasNext]   = useState(false);
  const [filter, setFilter]     = useState('all');

  const FILTERS = ['all', 'pending', 'in_progress', 'completed'];

  const load = async (pg = 1, append = false) => {
    try {
      const data = await getMyReports(pg, 15);
      setReports(prev => append ? [...prev, ...(data.reports || [])] : (data.reports || []));
      setHasNext(data.has_next);
      setPage(pg);
    } finally {
      setLoading(false);
    }
  };

  useFocusEffect(useCallback(() => { setLoading(true); load(1); }, []));

  const filtered = filter === 'all' ? reports : reports.filter(r => r.status === filter);

  const renderItem = ({ item: r }) => (
    <TouchableOpacity style={s.card} onPress={() => navigation.navigate('ReportDetail', { reportId: r.id })}>
      <View style={[s.line, { backgroundColor: SEV[r.severity] || '#9e9e9e' }]} />
      <View style={{ flex: 1 }}>
        <View style={s.row}>
          <Text style={s.cls}>{r.primary_class?.replace('_', ' ')}</Text>
          <View style={[s.badge, { backgroundColor: STAT[r.status] + '22' }]}>
            <Text style={[s.badgeT, { color: STAT[r.status] }]}>{r.status?.replace('_', ' ')}</Text>
          </View>
        </View>
        <Text style={s.date}>{r.created_at ? format(new Date(r.created_at), 'dd MMM yyyy • HH:mm') : ''}</Text>
        <View style={s.row}>
          <Text style={s.conf}>{Math.round((r.confidence || 0) * 100)}% confidence</Text>
          {r.reward_tokens > 0 && (
            <View style={s.token}><Ionicons name="star" size={12} color="#ffd600" /><Text style={s.tokenT}>+{r.reward_tokens}</Text></View>
          )}
        </View>
      </View>
      <Ionicons name="chevron-forward" size={16} color="#bdbdbd" />
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}><Text style={s.title}>My Reports</Text></View>

      {/* Filter tabs */}
      <View style={s.filters}>
        {FILTERS.map(f => (
          <TouchableOpacity key={f} style={[s.filterBtn, filter === f && s.filterActive]} onPress={() => setFilter(f)}>
            <Text style={[s.filterT, filter === f && s.filterActiveT]}>{f.replace('_', ' ')}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator color="#1a237e" />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={i => i.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: 12 }}
          ListEmptyComponent={
            <View style={s.empty}>
              <Ionicons name="document-outline" size={48} color="#bdbdbd" />
              <Text style={s.emptyT}>No reports found</Text>
            </View>
          }
          onEndReached={() => hasNext && load(page + 1, true)}
          onEndReachedThreshold={0.3}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: '#f5f5f5' },
  header: { backgroundColor: '#1a237e', padding: 20, paddingTop: 12 },
  title:  { color: '#fff', fontSize: 22, fontWeight: '800' },
  filters: { flexDirection: 'row', padding: 12, gap: 8 },
  filterBtn: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20,
               backgroundColor: '#fff', borderWidth: 1, borderColor: '#e0e0e0' },
  filterActive:  { backgroundColor: '#1a237e', borderColor: '#1a237e' },
  filterT:       { fontSize: 12, color: '#757575', fontWeight: '600', textTransform: 'capitalize' },
  filterActiveT: { color: '#fff' },
  card:  { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 12,
           marginBottom: 8, padding: 14, gap: 10, overflow: 'hidden',
           shadowColor: '#000', shadowOpacity: 0.05, elevation: 1 },
  line:  { width: 4, height: '100%', borderRadius: 2, position: 'absolute', left: 0 },
  row:   { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  cls:   { fontWeight: '700', color: '#212121', fontSize: 14 },
  date:  { color: '#9e9e9e', fontSize: 11, marginVertical: 3 },
  conf:  { color: '#757575', fontSize: 12 },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12 },
  badgeT: { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  token: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  tokenT: { color: '#e65100', fontWeight: '700', fontSize: 12 },
  empty:  { alignItems: 'center', padding: 48 },
  emptyT: { color: '#9e9e9e', marginTop: 12 },
});
