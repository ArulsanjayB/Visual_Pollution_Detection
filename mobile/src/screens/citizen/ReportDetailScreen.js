import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Image,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { getReport, requestXAI, absoluteUrl } from '../../config/api';
import { format } from 'date-fns';
import { BASE_URL } from '../../config/api';

const SEV_COLOR = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' };
const STA_COLOR = { pending: '#1565c0', in_progress: '#e65100', completed: '#2e7d32', rejected: '#b71c1c' };

export default function ReportDetailScreen({ route }) {
  const { reportId } = route.params;
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [xaiTab, setXaiTab]   = useState('overlay');   // 'overlay' | 'heatmap' | 'info'
  const [xaiReq, setXaiReq]   = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const data = await getReport(reportId);
      setReport(data);
    } catch (e) {
      Alert.alert('Error', 'Failed to load report');
    } finally {
      setLoading(false);
    }
  };

  const handleRequestZooLime = async () => {
    setXaiReq(true);
    try {
      await requestXAI(reportId, 'zoolime');
      Alert.alert('ZooLime Requested', 'ZooLime fusion is being generated. Check back in ~2 minutes.');
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setXaiReq(false);
    }
  };

  if (loading) return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
      <ActivityIndicator size="large" color="#1a237e" />
    </View>
  );
  if (!report) return null;

  const inf     = report.inference || {};
  const xai     = inf.xai || {};
  const sevColor = SEV_COLOR[inf.severity] || '#757575';
  const staColor = STA_COLOR[report.status] || '#757575';
  const date     = report.created_at ? format(new Date(report.created_at), 'dd MMM yyyy, HH:mm') : '';

  // XAI image URLs
  const methodName = xai.method || 'gradcam';
  const overlayUrl = report[`${methodName}_url`] || report.zoolime_url || report.lime_url || report.shap_url || report.gradcam_url;
  const overlayB64 = xai.overlay_b64;
  const xaiImgSrc  = overlayUrl
    ? { uri: overlayUrl.startsWith('/') ? `${BASE_URL}${overlayUrl}` : overlayUrl }
    : overlayB64
    ? { uri: `data:image/png;base64,${overlayB64}` }
    : null;

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll}>

        {/* Original Image */}
        {report.image_url && (
          <Image source={{ uri: absoluteUrl(report.image_url) }} style={s.mainImage} resizeMode="cover" />
        )}

        {/* Status banner */}
        <View style={[s.statusBanner, { backgroundColor: staColor }]}>
          <Ionicons name="information-circle" size={18} color="#fff" />
          <Text style={s.statusText}>{report.status?.replace('_', ' ').toUpperCase()}</Text>
          {report.reward_issued && (
            <View style={s.rewardBadge}>
              <Ionicons name="star" size={14} color="#ffd600" />
              <Text style={s.rewardBadgeText}>+{report.reward_tokens} tokens</Text>
            </View>
          )}
        </View>

        {/* Detection Summary */}
        <View style={s.card}>
          <Text style={s.cardTitle}>AI Detection Result</Text>
          <View style={s.detRow}>
            <View style={[s.sevBadge, { backgroundColor: sevColor }]}>
              <Text style={s.sevText}>{inf.severity}</Text>
            </View>
            <Text style={s.detClass}>{inf.primary_class?.replace('_', ' ')}</Text>
            <Text style={s.detConf}>{Math.round((inf.confidence || 0) * 100)}%</Text>
          </View>
          <View style={s.metaGrid}>
            <MetaItem icon="layers"       label="Detections"   value={String(inf.num_detections || 0)} />
            <MetaItem icon="timer"        label="Inference"     value={`${inf.inference_time_ms || 0}ms`} />
            <MetaItem icon="flask"        label="XAI Method"   value={(xai.method || 'N/A').toUpperCase()} />
            <MetaItem icon="trending-up"  label="Priority"     value={String(report.priority_score || 0)} />
          </View>
        </View>

        {/* XAI Visualization */}
        <View style={s.card}>
          <View style={s.xaiHeader}>
            <Text style={s.cardTitle}>Explainable AI (XAI)</Text>
            {!report.zoolime_url && (
              <TouchableOpacity style={s.zlBtn} onPress={handleRequestZooLime} disabled={xaiReq}>
                {xaiReq ? <ActivityIndicator size="small" color="#1a237e" /> :
                  <Text style={s.zlBtnText}>Request ZooLime</Text>}
              </TouchableOpacity>
            )}
          </View>

          {/* XAI tabs */}
          <View style={s.tabRow}>
            {['overlay', 'info'].map(t => (
              <TouchableOpacity key={t} style={[s.tab, xaiTab === t && s.tabActive]} onPress={() => setXaiTab(t)}>
                <Text style={[s.tabText, xaiTab === t && s.tabTextActive]}>{t.charAt(0).toUpperCase() + t.slice(1)}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {xaiTab === 'overlay' ? (
            xaiImgSrc ? (
              <Image source={xaiImgSrc} style={s.xaiImage} resizeMode="contain" />
            ) : (
              <View style={s.noXai}>
                <Ionicons name="image-outline" size={40} color="#bdbdbd" />
                <Text style={s.noXaiText}>XAI visualization not available</Text>
              </View>
            )
          ) : (
            <XAIInfoPanel xai={xai} report={report} />
          )}
        </View>

        {/* Location */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Location</Text>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
            <Ionicons name="location" size={18} color="#c62828" />
            <View style={{ flex: 1 }}>
              <Text style={s.locAddr}>{report.location?.address || 'Address not available'}</Text>
              <Text style={s.locCoords}>
                {report.location?.latitude?.toFixed(6)}, {report.location?.longitude?.toFixed(6)}
              </Text>
              <Text style={s.locSource}>Source: {report.location?.source?.toUpperCase() || 'GPS'}</Text>
            </View>
          </View>
        </View>

        {/* Description */}
        {report.description ? (
          <View style={s.card}>
            <Text style={s.cardTitle}>Your Description</Text>
            <Text style={s.descText}>{report.description}</Text>
          </View>
        ) : null}

        {/* Municipal notes */}
        {report.municipal_notes ? (
          <View style={[s.card, { borderLeftWidth: 4, borderLeftColor: '#1565c0' }]}>
            <Text style={[s.cardTitle, { color: '#1565c0' }]}>Municipal Notes</Text>
            <Text style={s.descText}>{report.municipal_notes}</Text>
          </View>
        ) : null}

        <Text style={s.footer}>Submitted: {date}</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function MetaItem({ icon, label, value }) {
  return (
    <View style={s.metaItem}>
      <Ionicons name={icon} size={14} color="#9e9e9e" />
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={s.metaValue}>{value}</Text>
    </View>
  );
}

function XAIInfoPanel({ xai, report }) {
  const method  = (xai.method || 'gradcam').toUpperCase();
  const inf = report.inference || {};
  const primaryClass = inf.primary_class?.replace('_', ' ') || 'Visual Pollution';
  const conf = Math.round((inf.confidence || 0) * 100);
  const numDet = inf.num_detections || 0;

  return (
    <View>
      <Text style={s.xaiDesc}>
        The AI analyzed the image using the {method} method and confirmed the presence of {primaryClass}. The highlighted regions in the overlay indicate exactly which parts of the image the AI used to make this decision.
      </Text>
      <View style={s.fusionParams}>
        <Text style={s.fusionTitle}>Problem Summary</Text>
        <Text style={s.fusionRow}>Primary Issue: {primaryClass}</Text>
        <Text style={s.fusionRow}>Confidence: {conf}%</Text>
        <Text style={s.fusionRow}>Total Objects Detected: {numDet}</Text>
        <Text style={s.fusionRow}>Severity Level: {inf.severity || 'UNKNOWN'}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  safe:      { flex: 1, backgroundColor: '#f5f5f5' },
  scroll:    { paddingBottom: 40 },
  mainImage: { width: '100%', height: 240 },

  statusBanner: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 8 },
  statusText:   { color: '#fff', fontWeight: '700', flex: 1, fontSize: 14 },
  rewardBadge:  { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(0,0,0,0.3)',
                  paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, gap: 4 },
  rewardBadgeText: { color: '#ffd600', fontWeight: '700', fontSize: 12 },

  card:      { backgroundColor: '#fff', margin: 12, marginTop: 8, borderRadius: 14, padding: 16,
               shadowColor: '#000', shadowOpacity: 0.06, shadowRadius: 4, elevation: 2 },
  cardTitle: { fontSize: 15, fontWeight: '800', color: '#212121', marginBottom: 12 },

  detRow:  { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 },
  sevBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  sevText:  { color: '#fff', fontWeight: '800', fontSize: 13 },
  detClass: { fontSize: 16, fontWeight: '700', color: '#212121', flex: 1 },
  detConf:  { fontSize: 18, fontWeight: '900', color: '#1a237e' },

  metaGrid:  { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metaItem:  { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#f5f5f5',
               paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20 },
  metaLabel: { fontSize: 11, color: '#9e9e9e' },
  metaValue: { fontSize: 11, fontWeight: '700', color: '#212121' },

  xaiHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  zlBtn:     { backgroundColor: '#e8eaf6', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20 },
  zlBtnText: { color: '#1a237e', fontWeight: '700', fontSize: 12 },

  tabRow:     { flexDirection: 'row', backgroundColor: '#f5f5f5', borderRadius: 10, padding: 3, marginBottom: 12 },
  tab:        { flex: 1, alignItems: 'center', paddingVertical: 8, borderRadius: 8 },
  tabActive:  { backgroundColor: '#1a237e' },
  tabText:    { fontSize: 13, color: '#9e9e9e', fontWeight: '600' },
  tabTextActive: { color: '#fff' },

  xaiImage: { width: '100%', height: 240, borderRadius: 10, backgroundColor: '#000' },
  noXai:    { alignItems: 'center', padding: 32 },
  noXaiText: { color: '#9e9e9e', marginTop: 10 },
  xaiDesc:  { fontSize: 13, color: '#616161', lineHeight: 20 },
  fusionParams: { marginTop: 12, backgroundColor: '#f5f5f5', borderRadius: 10, padding: 12 },
  fusionTitle:  { fontWeight: '700', color: '#1a237e', marginBottom: 8 },
  fusionRow:    { fontSize: 12, color: '#424242', paddingVertical: 2 },

  locAddr:   { fontSize: 14, color: '#212121', fontWeight: '600' },
  locCoords: { fontSize: 12, color: '#9e9e9e', marginTop: 2 },
  locSource: { fontSize: 11, color: '#bdbdbd', marginTop: 2 },
  descText:  { fontSize: 13, color: '#424242', lineHeight: 20 },
  footer:    { textAlign: 'center', color: '#bdbdbd', fontSize: 12, margin: 20 },
});
