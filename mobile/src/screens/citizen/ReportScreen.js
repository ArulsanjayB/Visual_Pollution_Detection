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
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { Ionicons } from '@expo/vector-icons';
import { submitReport } from '../../config/api';

const XAI_OPTIONS = [
  { key: 'gradcam', label: 'Grad-CAM', desc: 'Fast heatmap (~2s, instant)', icon: 'flame' },
  { key: 'zoolime', label: 'ZooLime', desc: 'Full fusion (generates in background)', icon: 'git-merge' },
  { key: 'lime',    label: 'LIME',    desc: 'Superpixel analysis (generates in background)', icon: 'grid' },
  { key: 'none',    label: 'None',    desc: 'Detection only', icon: 'close-circle-outline' },
];

export default function ReportScreen({ navigation }) {
  const [imageUri, setImageUri]       = useState(null);
  const [location, setLocation]       = useState(null);
  const [locLoading, setLocLoading]   = useState(false);
  const [description, setDescription] = useState('');
  const [xaiMode, setXaiMode]         = useState('gradcam');
  const [submitting, setSubmitting]   = useState(false);
  const [progress, setProgress]       = useState(0);
  const [result, setResult]           = useState(null);
  const [showXAIModal, setShowXAIModal] = useState(false);

  // Auto-get location when screen loads
  useEffect(() => { fetchLocation(); }, []);

  const fetchLocation = async () => {
    setLocLoading(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Location Required', 'Please enable location access to tag your report.');
        return;
      }
      const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      // Reverse geocode
      const [addr] = await Location.reverseGeocodeAsync(loc.coords);
      setLocation({
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
        address: [addr.street, addr.city, addr.region].filter(Boolean).join(', '),
        source: 'gps',
      });
    } catch (e) {
      Alert.alert('Location Error', 'Could not get location. You can still submit without it.');
    } finally {
      setLocLoading(false);
    }
  };

  const pickImage = async (fromCamera = false) => {
    const { status } = fromCamera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', `Please allow ${fromCamera ? 'camera' : 'gallery'} access.`);
      return;
    }
    const pickerFn = fromCamera ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
    const res = await pickerFn({ mediaTypes: ['images'],
                                  quality: 0.85, allowsEditing: false });
    if (!res.canceled && res.assets?.length > 0) {
      setImageUri(res.assets[0].uri);
      setResult(null); // reset previous result
    }
  };

  const handleSubmit = async () => {
    if (!imageUri) {
      Alert.alert('Image Required', 'Please select or take a photo first.');
      return;
    }
    if (!location) {
      Alert.alert('Location Missing', 'Getting location… Please wait or retry.');
      return;
    }

    setSubmitting(true);
    setProgress(0);
    try {
      const data = await submitReport(imageUri, location, description, xaiMode, setProgress);
      setResult(data);
    } catch (e) {
      Alert.alert('Submission Failed', e.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setImageUri(null); setResult(null); setDescription(''); setProgress(0);
  };

  // ── Result Screen ─────────────────────────────────────────────────────────
  if (result) {
    const isProcessing = result.processing || result.primary_class === 'Processing...';
    const sevColor = { HIGH: '#c62828', MEDIUM: '#f57f17', LOW: '#2e7d32' }[result.severity] || '#757575';
    return (
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={{ padding: 20 }}>
          <View style={s.resultHeader}>
            <Ionicons
              name={isProcessing ? "cloud-upload" : "checkmark-circle"}
              size={56}
              color={isProcessing ? "#1a237e" : "#2e7d32"}
            />
            <Text style={s.resultTitle}>
              {isProcessing ? "Report Received!" : "Report Submitted!"}
            </Text>
            <Text style={s.resultId}>ID: {result.report_id?.slice(0, 8).toUpperCase()}</Text>
          </View>

          {isProcessing ? (
            <View style={s.urgentBanner}>
              <Ionicons name="hourglass-outline" size={20} color="#fff" />
              <Text style={s.urgentText}>
                Your image is uploading and the AI is analyzing it in the background.
                You can safely close this screen — the report will appear in your history
                once processing finishes (~30-90 seconds).
              </Text>
            </View>
          ) : (
            <>
              <View style={[s.resultCard, { borderTopColor: sevColor }]}>
                <Row icon="scan" label="Detected"   value={result.primary_class?.replace('_', ' ')} />
                <Row icon="speedometer" label="Confidence" value={`${Math.round(result.confidence * 100)}%`} />
                <Row icon="alert" label="Severity"  value={result.severity} valueColor={sevColor} />
                <Row icon="copy" label="Detections" value={String(result.num_detections)} />
                <Row icon="flask" label="XAI Method" value={result.xai_method?.toUpperCase()} />
              </View>

              {result.xai_queued && (
                <View style={s.urgentBanner}>
                  <Ionicons name="hourglass-outline" size={20} color="#fff" />
                  <Text style={s.urgentText}>
                    {(result.xai_queued_method || 'XAI').toUpperCase()} explanation is generating in the
                    background. Check the report detail in ~60-90 seconds.
                  </Text>
                </View>
              )}
            </>
          )}

          <TouchableOpacity style={s.viewBtn}
            onPress={() => navigation.navigate('ReportDetail', { reportId: result.report_id })}>
            <Text style={s.viewBtnText}>
              {isProcessing ? "View Report (may still be processing)" : "View Full Report & XAI"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.newBtn} onPress={resetForm}>
            <Text style={s.newBtnText}>Submit Another Report</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── Form ─────────────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.form} keyboardShouldPersistTaps="handled">
        <Text style={s.pageTitle}>Submit Report</Text>

        {/* Image picker */}
        <Text style={s.label}>Photo *</Text>
        {imageUri ? (
          <View>
            <Image source={{ uri: imageUri }} style={s.preview} resizeMode="cover" />
            <TouchableOpacity style={s.changePhoto} onPress={() => pickImage(false)}>
              <Ionicons name="refresh" size={16} color="#1a237e" />
              <Text style={s.changePhotoText}>Change Photo</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={s.pickerRow}>
            <TouchableOpacity style={[s.pickerBtn, { flex: 1 }]} onPress={() => pickImage(true)}>
              <Ionicons name="camera" size={28} color="#1a237e" />
              <Text style={s.pickerText}>Camera</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.pickerBtn, { flex: 1 }]} onPress={() => pickImage(false)}>
              <Ionicons name="images" size={28} color="#1a237e" />
              <Text style={s.pickerText}>Gallery</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Location */}
        <Text style={s.label}>Location</Text>
        <TouchableOpacity style={s.locBox} onPress={fetchLocation}>
          {locLoading ? (
            <ActivityIndicator color="#1a237e" />
          ) : location ? (
            <>
              <Ionicons name="location" size={18} color="#2e7d32" />
              <Text style={[s.locText, { color: '#2e7d32' }]} numberOfLines={2}>
                {location.address || `${location.latitude.toFixed(5)}, ${location.longitude.toFixed(5)}`}
              </Text>
              <Ionicons name="refresh" size={16} color="#9e9e9e" />
            </>
          ) : (
            <>
              <Ionicons name="location-outline" size={18} color="#9e9e9e" />
              <Text style={s.locText}>Tap to get current location</Text>
            </>
          )}
        </TouchableOpacity>

        {/* XAI mode */}
        <Text style={s.label}>Explanation Method</Text>
        <TouchableOpacity style={s.xaiSelector} onPress={() => setShowXAIModal(true)}>
          <Ionicons name="flask" size={18} color="#1a237e" />
          <Text style={s.xaiText}>
            {XAI_OPTIONS.find(x => x.key === xaiMode)?.label} —{' '}
            {XAI_OPTIONS.find(x => x.key === xaiMode)?.desc}
          </Text>
          <Ionicons name="chevron-down" size={16} color="#9e9e9e" />
        </TouchableOpacity>

        {/* Description */}
        <Text style={s.label}>Description (optional)</Text>
        <TextInput
          style={s.textArea}
          placeholder="Describe what you see…"
          value={description}
          onChangeText={setDescription}
          multiline
          numberOfLines={3}
          maxLength={500}
        />

        {/* Submit */}
        <TouchableOpacity style={[s.submitBtn, submitting && { opacity: 0.7 }]}
          onPress={handleSubmit} disabled={submitting}>
          {submitting ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <ActivityIndicator color="#fff" />
              <Text style={s.submitText}>{progress > 0 ? `Uploading ${progress}%…` : 'Analyzing…'}</Text>
            </View>
          ) : (
            <>
              <Ionicons name="send" size={20} color="#fff" />
              <Text style={s.submitText}>Submit Report</Text>
            </>
          )}
        </TouchableOpacity>
      </ScrollView>

      {/* XAI modal */}
      <Modal visible={showXAIModal} transparent animationType="slide"
        onRequestClose={() => setShowXAIModal(false)}>
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <Text style={s.modalTitle}>Select Explanation Method</Text>
            {XAI_OPTIONS.map(opt => (
              <TouchableOpacity key={opt.key} style={[s.xaiOption, xaiMode === opt.key && s.xaiOptionActive]}
                onPress={() => { setXaiMode(opt.key); setShowXAIModal(false); }}>
                <Ionicons name={opt.icon} size={22} color={xaiMode === opt.key ? '#1a237e' : '#757575'} />
                <View style={{ flex: 1, marginLeft: 14 }}>
                  <Text style={[s.xaiOptLabel, xaiMode === opt.key && { color: '#1a237e' }]}>{opt.label}</Text>
                  <Text style={s.xaiOptDesc}>{opt.desc}</Text>
                </View>
                {xaiMode === opt.key && <Ionicons name="checkmark-circle" size={20} color="#1a237e" />}
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function Row({ icon, label, value, valueColor }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' }}>
      <Ionicons name={icon} size={16} color="#9e9e9e" style={{ marginRight: 10 }} />
      <Text style={{ flex: 1, color: '#616161', fontSize: 13 }}>{label}</Text>
      <Text style={{ fontWeight: '700', color: valueColor || '#212121', fontSize: 13 }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe:  { flex: 1, backgroundColor: '#f5f5f5' },
  form:  { padding: 20, paddingBottom: 40 },
  pageTitle: { fontSize: 22, fontWeight: '800', color: '#1a237e', marginBottom: 20 },
  label: { fontSize: 13, fontWeight: '600', color: '#616161', marginTop: 16, marginBottom: 8 },

  pickerRow: { flexDirection: 'row', gap: 12 },
  pickerBtn: { backgroundColor: '#fff', borderRadius: 12, borderWidth: 2, borderStyle: 'dashed',
               borderColor: '#c5cae9', alignItems: 'center', justifyContent: 'center', padding: 24 },
  pickerText: { color: '#1a237e', fontWeight: '600', marginTop: 8, fontSize: 13 },
  preview:   { width: '100%', height: 220, borderRadius: 12 },
  changePhoto: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                 gap: 6, marginTop: 8, padding: 8 },
  changePhotoText: { color: '#1a237e', fontWeight: '600' },

  locBox:  { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 10,
             padding: 14, gap: 10, borderWidth: 1, borderColor: '#e0e0e0' },
  locText: { flex: 1, color: '#616161', fontSize: 13 },

  xaiSelector: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#fff', borderRadius: 10,
                  padding: 14, gap: 10, borderWidth: 1, borderColor: '#c5cae9' },
  xaiText:  { flex: 1, color: '#212121', fontSize: 13 },

  textArea: { backgroundColor: '#fff', borderRadius: 10, borderWidth: 1, borderColor: '#e0e0e0',
              padding: 12, fontSize: 14, minHeight: 80, textAlignVertical: 'top' },

  submitBtn:  { backgroundColor: '#1a237e', borderRadius: 12, padding: 16, flexDirection: 'row',
                alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 24 },
  submitText: { color: '#fff', fontSize: 16, fontWeight: '700' },

  // Result
  resultHeader: { alignItems: 'center', paddingVertical: 20 },
  resultTitle:  { fontSize: 24, fontWeight: '800', color: '#2e7d32', marginTop: 12 },
  resultId:     { color: '#9e9e9e', marginTop: 4 },
  resultCard:   { backgroundColor: '#fff', borderRadius: 14, padding: 18, borderTopWidth: 4, marginVertical: 16 },
  urgentBanner: { backgroundColor: '#c62828', borderRadius: 10, padding: 12, flexDirection: 'row',
                  gap: 10, alignItems: 'center', marginBottom: 16 },
  urgentText:   { color: '#fff', fontSize: 12, flex: 1 },
  viewBtn:  { backgroundColor: '#1a237e', borderRadius: 12, padding: 16, alignItems: 'center', marginBottom: 10 },
  viewBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  newBtn:   { borderWidth: 2, borderColor: '#1a237e', borderRadius: 12, padding: 14, alignItems: 'center' },
  newBtnText: { color: '#1a237e', fontSize: 15, fontWeight: '600' },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modalSheet:   { backgroundColor: '#fff', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  modalTitle:   { fontSize: 17, fontWeight: '800', color: '#212121', marginBottom: 16 },
  xaiOption:    { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12,
                  borderWidth: 1.5, borderColor: '#e0e0e0', marginBottom: 10 },
  xaiOptionActive: { borderColor: '#1a237e', backgroundColor: '#e8eaf6' },
  xaiOptLabel:  { fontWeight: '700', color: '#212121', fontSize: 14 },
  xaiOptDesc:   { color: '#9e9e9e', fontSize: 12, marginTop: 2 },
});
