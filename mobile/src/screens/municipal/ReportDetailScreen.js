import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  Image,
  Alert,
  ActivityIndicator,
  Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { getMunicipalReport, updateReportStatus, absoluteUrl, deleteReport } from '../../config/api';
import { BASE_URL } from '../../config/api';
import { useAuth } from '../../context/AuthContext';
import { format } from 'date-fns';

const SEV_CLR  = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' };
const STATUS_OPTIONS = [
  { key: 'pending',     label: 'Pending',     icon: 'time',              color: '#1565c0' },
  { key: 'in_progress', label: 'In Progress', icon: 'construct',         color: '#e65100' },
  { key: 'completed',   label: 'Completed',   icon: 'checkmark-circle',  color: '#2e7d32' },
  { key: 'rejected',    label: 'Rejected',    icon: 'close-circle',      color: '#b71c1c' },
];

export default function MunicipalDetailScreen({ route, navigation }) {
  const { reportId } = route.params;
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  
  const [report,     setReport]     = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [saving,     setSaving]     = useState(false);
  const [notes,      setNotes]      = useState('');
  const [showStatus, setShowStatus] = useState(false);
  const [xaiView,    setXaiView]    = useState('overlay'); // overlay | heatmap | info
  const [showZooLime, setShowZooLime] = useState(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const data = await getMunicipalReport(reportId);
      setReport(data);
      setNotes(data.municipal_notes || '');
    } catch (e) {
      Alert.alert('Error', 'Failed to load report details');
    } finally {
      setLoading(false);
    }
  };

  const saveUpdate = async (statusOverride) => {
    setSaving(true);
    try {
      await updateReportStatus(reportId, {
        status:          statusOverride || report.status,
        municipal_notes: notes,
      });
      Alert.alert('Saved', 'Report updated successfully');
      load();
    } catch (e) {
      Alert.alert('Update failed', e.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
      <ActivityIndicator size="large" color="#1a237e" />
    </View>
  );
  if (!report) return null;

  const inf      = report.inference || {};
  const xai      = inf.xai || {};
  const xaiMeta  = xai.metadata || {};
  const sevColor = SEV_CLR[inf.severity] || '#757575';
  const date     = report.created_at
    ? format(new Date(report.created_at), 'dd MMM yyyy, HH:mm')
    : '';

  // Image sources
  const origImg    = report.image_url ? { uri: absoluteUrl(report.image_url) } : null;
  const methodName = xai.method || 'gradcam';
  const overlayUrl = report[`${methodName}_url`] || report.zoolime_url || report.lime_url || report.shap_url || report.gradcam_url;
  const xaiImgSrc  = overlayUrl
    ? { uri: overlayUrl.startsWith('/') ? `${BASE_URL}${overlayUrl}` : overlayUrl }
    : xai.overlay_b64
    ? { uri: `data:image/png;base64,${xai.overlay_b64}` }
    : null;

  const currentStatus = STATUS_OPTIONS.find(s => s.key === report.status) || STATUS_OPTIONS[0];

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll}>

        {/* Image gallery: original + XAI toggle */}
        <View style={s.imagePanel}>
          {/* Tabs */}
          <View style={s.imgTabRow}>
            {['Original', 'XAI View'].map((t, i) => (
              <TouchableOpacity key={t}
                style={[s.imgTab, xaiView === (i === 0 ? 'original' : 'overlay') && s.imgTabActive]}
                onPress={() => setXaiView(i === 0 ? 'original' : 'overlay')}>
                <Text style={[s.imgTabT, xaiView === (i === 0 ? 'original' : 'overlay') && s.imgTabTA]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {xaiView === 'original' ? (
            origImg
              ? <Image source={origImg} style={s.mainImg} resizeMode="cover" />
              : <View style={s.noImg}><Ionicons name="image-outline" size={48} color="#bdbdbd" /><Text style={s.noImgT}>No image</Text></View>
          ) : (
            xaiImgSrc
              ? <Image source={xaiImgSrc} style={s.mainImg} resizeMode="contain" />
              : <View style={s.noImg}>
                  <Ionicons name="flask-outline" size={48} color="#bdbdbd" />
                  <Text style={s.noImgT}>XAI image not yet generated</Text>
                </View>
          )}
        </View>

        {/* Detection results */}
        <View style={s.card}>
          <View style={s.cardHead}>
            <Text style={s.cardTitle}>AI Detection</Text>
            <View style={[s.sevPill, { backgroundColor: sevColor }]}>
              <Text style={s.sevPillT}>{inf.severity} SEVERITY</Text>
            </View>
          </View>

          <View style={s.detGrid}>
            <DetCell icon="scan"         label="Type"        value={inf.primary_class?.replace('_', ' ')} big />
            <DetCell icon="speedometer"  label="Confidence"  value={`${Math.round((inf.confidence || 0) * 100)}%`} />
            <DetCell icon="layers"       label="Detections"  value={String(inf.num_detections || 0)} />
            <DetCell icon="trending-up"  label="Priority"    value={`${Math.round(report.priority_score || 0)}/100`} />
            <DetCell icon="flask"        label="XAI Method"  value={(xai.method || 'N/A').toUpperCase()} />
            <DetCell icon="timer"        label="Inference"   value={`${inf.inference_time_ms || 0}ms`} />
          </View>
        </View>

        {/* XAI Explanation panel */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Explainable AI Summary</Text>
          <XAIExplanation method={xai.method} meta={xaiMeta}
            hasZooLime={!!report.zoolime_url}
            onRequestZooLime={() => setShowZooLime(true)}
            report={report} />
        </View>

        {/* Per-detection boxes */}
        {inf.detections && inf.detections.length > 0 && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Detection Boxes</Text>
            {inf.detections.map((d, i) => (
              <View key={i} style={s.detBox}>
                <Text style={s.detBoxCls}>#{i+1} {d.class_name}</Text>
                <Text style={s.detBoxConf}>{Math.round(d.confidence * 100)}%</Text>
                <Text style={s.detBoxBbox}>
                  [{d.bbox?.map(v => Math.round(v)).join(', ')}]
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Location */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Location</Text>
          <View style={s.locRow}>
            <Ionicons name="location" size={18} color="#c62828" />
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={s.locAddr}>{report.location?.address || 'No address'}</Text>
              <Text style={s.locCoords}>
                {report.location?.latitude?.toFixed(6)}, {report.location?.longitude?.toFixed(6)}
              </Text>
              <Text style={s.locSrc}>Source: {(report.location?.source || 'gps').toUpperCase()}</Text>
            </View>
          </View>
        </View>

        {/* Citizen info */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Citizen</Text>
          <Row icon="person"    label="Name"     value={report.citizen_name || 'Unknown'} />
          <Row icon="time"      label="Reported" value={date} />
          {report.description && <Row icon="chatbubble" label="Note" value={report.description} />}
        </View>

        {/* Status update */}
        <View style={s.card}>
          <Text style={s.cardTitle}>Update Status</Text>
          <TouchableOpacity style={[s.statusSelector, { borderColor: currentStatus.color }]}
            onPress={() => setShowStatus(true)}>
            <Ionicons name={currentStatus.icon} size={18} color={currentStatus.color} />
            <Text style={[s.statusSelectorT, { color: currentStatus.color }]}>{currentStatus.label}</Text>
            <Ionicons name="chevron-down" size={16} color="#9e9e9e" />
          </TouchableOpacity>

          <Text style={s.label}>Municipal Notes</Text>
          <TextInput
            style={s.notesInput}
            placeholder="Add notes for the team or citizen…"
            value={notes}
            onChangeText={setNotes}
            multiline
            numberOfLines={4}
            textAlignVertical="top"
          />

          <TouchableOpacity style={s.saveBtn} onPress={() => saveUpdate()} disabled={saving}>
            {saving ? <ActivityIndicator color="#fff" /> :
              <><Ionicons name="save" size={18} color="#fff" /><Text style={s.saveBtnT}>Save Changes</Text></>}
          </TouchableOpacity>

          {isAdmin && (
            <TouchableOpacity style={[s.saveBtn, { backgroundColor: '#d32f2f', marginTop: 12 }]} 
              onPress={() => {
                Alert.alert('Delete Report', 'Permanently delete this report?', [
                  { text: 'Cancel', style: 'cancel' },
                  { text: 'Delete', style: 'destructive', onPress: async () => {
                    try {
                      await deleteReport(reportId);
                      Alert.alert('Deleted', 'Report was deleted');
                      navigation.goBack();
                    } catch (e) {
                      Alert.alert('Error', e.message);
                    }
                  }}
                ]);
              }}>
              <Ionicons name="trash" size={18} color="#fff" />
              <Text style={s.saveBtnT}>Delete Report</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* PDF download note */}
        <View style={[s.card, { flexDirection: 'row', alignItems: 'center', gap: 12 }]}>
          <Ionicons name="document-text" size={28} color="#1a237e" />
          <View style={{ flex: 1 }}>
            <Text style={{ fontWeight: '700', color: '#1a237e' }}>Download PDF Report</Text>
            <Text style={{ fontSize: 12, color: '#757575', marginTop: 2 }}>
              Use the desktop dashboard or API endpoint POST /api/municipal/reports/{reportId}/pdf
            </Text>
          </View>
        </View>

      </ScrollView>

      {/* Status Modal */}
      <Modal visible={showStatus} transparent animationType="slide"
        onRequestClose={() => setShowStatus(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <Text style={s.modalTitle}>Change Status</Text>
            {STATUS_OPTIONS.map(opt => (
              <TouchableOpacity key={opt.key} style={s.statusOpt}
                onPress={() => { setShowStatus(false); saveUpdate(opt.key); }}>
                <Ionicons name={opt.icon} size={22} color={opt.color} />
                <Text style={[s.statusOptT, { color: opt.color }]}>{opt.label}</Text>
                {report.status === opt.key && <Ionicons name="checkmark" size={18} color={opt.color} />}
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function XAIExplanation({ method, meta, hasZooLime, onRequestZooLime, report }) {
  const methodUpper = (method || 'gradcam').toUpperCase();
  const inf = report?.inference || {};
  const primaryClass = inf.primary_class?.replace('_', ' ') || 'Visual Pollution';
  const conf = Math.round((inf.confidence || 0) * 100);
  const numDet = inf.num_detections || 0;

  return (
    <View>
      <Text style={s.xaiDesc}>
        The AI analyzed the image using {methodUpper} and confirmed the presence of {primaryClass}. The highlighted regions in the overlay indicate exactly which parts of the image the AI used to make this decision.
      </Text>
      <View style={s.fusionBox}>
        <Text style={s.fusionTitle}>Problem Summary</Text>
        <Text style={s.fusionRow}>Primary Issue: {primaryClass}</Text>
        <Text style={s.fusionRow}>Confidence: {conf}%</Text>
        <Text style={s.fusionRow}>Total Objects Detected: {numDet}</Text>
        <Text style={s.fusionRow}>Severity Level: {inf.severity || 'UNKNOWN'}</Text>
      </View>
      {!hasZooLime && method !== 'zoolime' && (
        <TouchableOpacity style={s.zlReqBtn} onPress={onRequestZooLime}>
          <Ionicons name="git-merge" size={16} color="#1a237e" />
          <Text style={s.zlReqT}>Generate ZooLime Fusion (recommended)</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

function Row({ icon, label, value }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 6,
                   borderBottomWidth: 1, borderColor: '#f5f5f5' }}>
      <Ionicons name={icon} size={14} color="#9e9e9e" style={{ marginRight: 8, marginTop: 2 }} />
      <Text style={{ width: 70, color: '#9e9e9e', fontSize: 12 }}>{label}</Text>
      <Text style={{ flex: 1, color: '#212121', fontSize: 13 }}>{value}</Text>
    </View>
  );
}

function DetCell({ icon, label, value, big }) {
  return (
    <View style={[s.detCell, big && { width: '100%' }]}>
      <Ionicons name={icon} size={13} color="#9e9e9e" />
      <Text style={s.detCellL}>{label}</Text>
      <Text style={s.detCellV}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: '#f5f5f5' },
  scroll: { paddingBottom: 40 },

  imagePanel: { backgroundColor: '#000' },
  imgTabRow:  { flexDirection: 'row', backgroundColor: '#1a1a1a' },
  imgTab:     { flex: 1, alignItems: 'center', paddingVertical: 10 },
  imgTabActive: { borderBottomWidth: 2, borderBottomColor: '#5c6bc0' },
  imgTabT:    { color: '#9e9e9e', fontSize: 13, fontWeight: '600' },
  imgTabTA:   { color: '#fff' },
  mainImg:    { width: '100%', height: 260, backgroundColor: '#111' },
  noImg:      { height: 200, justifyContent: 'center', alignItems: 'center', backgroundColor: '#1a1a1a' },
  noImgT:     { color: '#616161', marginTop: 10 },

  card:       { backgroundColor: '#fff', margin: 12, marginTop: 8, borderRadius: 14, padding: 16,
                shadowColor: '#000', shadowOpacity: 0.06, elevation: 2 },
  cardHead:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  cardTitle:  { fontSize: 15, fontWeight: '800', color: '#212121', marginBottom: 12 },
  sevPill:    { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  sevPillT:   { color: '#fff', fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },

  detGrid:    { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  detCell:    { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#f5f5f5',
                paddingHorizontal: 10, paddingVertical: 7, borderRadius: 20, width: '47%' },
  detCellL:   { fontSize: 10, color: '#9e9e9e' },
  detCellV:   { fontSize: 12, fontWeight: '700', color: '#212121', flex: 1, textAlign: 'right' },

  xaiDesc:    { fontSize: 13, color: '#424242', lineHeight: 20 },
  fusionBox:  { backgroundColor: '#e8eaf6', borderRadius: 10, padding: 12, marginTop: 12 },
  fusionTitle: { fontWeight: '800', color: '#1a237e', marginBottom: 8 },
  fusionRow:  { fontSize: 12, color: '#283593', paddingVertical: 2 },
  zlReqBtn:   { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12,
                backgroundColor: '#e8eaf6', borderRadius: 10, padding: 12 },
  zlReqT:     { color: '#1a237e', fontWeight: '600', fontSize: 13 },

  detBox:     { flexDirection: 'row', alignItems: 'center', paddingVertical: 7,
                borderBottomWidth: 1, borderColor: '#f0f0f0', gap: 8 },
  detBoxCls:  { fontWeight: '600', color: '#212121', fontSize: 13, flex: 1 },
  detBoxConf: { fontWeight: '700', color: '#1a237e', width: 42 },
  detBoxBbox: { color: '#9e9e9e', fontSize: 10 },

  locRow:     { flexDirection: 'row' },
  locAddr:    { fontWeight: '600', color: '#212121', fontSize: 14 },
  locCoords:  { color: '#9e9e9e', fontSize: 11, marginTop: 3 },
  locSrc:     { color: '#bdbdbd', fontSize: 11, marginTop: 2 },

  label:         { fontSize: 12, color: '#616161', fontWeight: '600', marginBottom: 8, marginTop: 12 },
  statusSelector: { flexDirection: 'row', alignItems: 'center', borderWidth: 2, borderRadius: 10,
                    padding: 12, gap: 10 },
  statusSelectorT: { flex: 1, fontWeight: '700', fontSize: 15 },
  notesInput:    { borderWidth: 1, borderColor: '#e0e0e0', borderRadius: 10, padding: 12,
                   fontSize: 13, minHeight: 90, backgroundColor: '#fafafa' },
  saveBtn:       { backgroundColor: '#1a237e', borderRadius: 10, padding: 14, flexDirection: 'row',
                   alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 14 },
  saveBtnT:      { color: '#fff', fontWeight: '700', fontSize: 15 },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet:   { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20,
                  padding: 24, paddingBottom: 44 },
  modalTitle:   { fontSize: 17, fontWeight: '800', color: '#212121', marginBottom: 16 },
  statusOpt:    { flexDirection: 'row', alignItems: 'center', gap: 16, padding: 16,
                  borderBottomWidth: 1, borderColor: '#f5f5f5' },
  statusOptT:   { fontSize: 15, fontWeight: '700', flex: 1 },
});
