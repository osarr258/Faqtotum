import { useState } from "react";
import { View, StyleSheet, Pressable, TextInput, ActivityIndicator, Platform } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import { useAudioRecorder, RecordingPresets, AudioModule, setAudioModeAsync } from "expo-audio";
import * as FileSystem from "expo-file-system/legacy";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import AIAnalyzing from "@/src/components/AIAnalyzing";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const URGENCY_COLORS: Record<string, string> = { faible: colors.success, moyenne: colors.warning, elevee: "#FB923C", urgence: colors.error };
const URGENCY_LABELS: Record<string, string> = { faible: "Faible", moyenne: "Modérée", elevee: "Élevée", urgence: "Urgence" };

type Diag = {
  problem: string; trade: string; trade_label: string; trade_icon: string; urgency: string;
  duration_min: number; duration_max: number; price_min: number; price_max: number;
  materials: string[]; causes: string[]; confidence: number; advice: string;
};

export default function Diagnose() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [diag, setDiag] = useState<Diag | null>(null);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState("");

  const pickImage = async (camera: boolean) => {
    setError("");
    const perm = camera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      setError(camera ? "Autorisez l'appareil photo dans les réglages." : "Autorisez l'accès aux photos dans les réglages.");
      return;
    }
    const res = camera
      ? await ImagePicker.launchCameraAsync({ base64: true, quality: 0.5 })
      : await ImagePicker.launchImageLibraryAsync({ base64: true, quality: 0.5, mediaTypes: ["images"] });
    if (!res.canceled && res.assets[0]?.base64) {
      setImages((p) => [...p, res.assets[0].base64 as string].slice(0, 3));
    }
  };

  const toggleRecord = async () => {
    setError("");
    if (recording) {
      try {
        await recorder.stop();
        setRecording(false);
        const uri = recorder.uri;
        if (!uri) return;
        setTranscribing(true);
        const ext = Platform.OS === "web" ? "webm" : "m4a";
        let b64: string;
        if (Platform.OS === "web") {
          const blob = await (await fetch(uri)).blob();
          b64 = await new Promise((resolve) => {
            const r = new FileReader();
            r.onloadend = () => resolve((r.result as string).split(",")[1]);
            r.readAsDataURL(blob);
          });
        } else {
          b64 = await FileSystem.readAsStringAsync(uri, { encoding: "base64" });
        }
        const out = await api<{ text: string }>("/ai/transcribe", { method: "POST", body: { audio_base64: b64, ext } });
        setText((prev) => (prev ? prev + " " : "") + out.text);
      } catch {
        setError("Transcription impossible. Réessayez.");
      } finally {
        setTranscribing(false);
      }
    } else {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) { setError("Autorisez le micro dans les réglages."); return; }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    }
  };

  const analyze = async () => {
    if (!text.trim() && images.length === 0) { setError("Décrivez le problème ou ajoutez une photo."); return; }
    setError(""); setAnalyzing(true); setDiag(null);
    try {
      const [d] = await Promise.all([
        api<Diag>("/ai/diagnose", { method: "POST", body: { text, images } }),
        new Promise((r) => setTimeout(r, 5200)),
      ]);
      setDiag(d as Diag);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const findPro = async () => {
    if (!diag) return;
    setMatching(true); setError("");
    try {
      const m = await api<{ mission_id: string }>("/missions", {
        method: "POST",
        body: { trade: diag.trade, urgency: diag.urgency, diagnosis: diag, price_min: diag.price_min, price_max: diag.price_max },
      });
      router.push({ pathname: "/matching/[id]", params: { id: m.mission_id } });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMatching(false);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-button" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Diagnostic IA</Txt>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAwareScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] }} bottomOffset={20} showsVerticalScrollIndicator={false}>
        {!diag && (
          <>
            <Txt weight="extrabold" size="2xl">Décrivez votre problème</Txt>
            <Txt color={colors.muted} style={{ marginTop: spacing.xs, marginBottom: spacing.lg }}>Texte, photos ou message vocal — notre IA analyse tout.</Txt>

            <View style={styles.textBox}>
              <TextInput
                testID="problem-text"
                value={text}
                onChangeText={setText}
                placeholder="Ex: ma chaudière fuit et ne chauffe plus…"
                placeholderTextColor={colors.muted}
                multiline
                style={styles.textInput}
              />
            </View>

            {images.length > 0 && (
              <View style={styles.thumbs}>
                {images.map((b, i) => (
                  <View key={i} style={styles.thumbWrap}>
                    <Image source={{ uri: `data:image/jpeg;base64,${b}` }} style={styles.thumb} contentFit="cover" />
                    <Pressable testID={`remove-img-${i}`} onPress={() => setImages((p) => p.filter((_, j) => j !== i))} style={styles.thumbX}>
                      <Ionicons name="close" size={14} color={colors.textInverse} />
                    </Pressable>
                  </View>
                ))}
              </View>
            )}

            <View style={styles.toolRow}>
              <Tool testID="add-photo" icon="image-outline" label="Galerie" onPress={() => pickImage(false)} />
              <Tool testID="take-photo" icon="camera-outline" label="Photo" onPress={() => pickImage(true)} />
              <Tool testID="voice-btn" icon={recording ? "stop-circle" : "mic-outline"} label={recording ? "Stop" : transcribing ? "…" : "Vocal"} active={recording} onPress={toggleRecord} />
            </View>

            {transcribing && <View style={styles.inline}><ActivityIndicator color={colors.brand} /><Txt color={colors.muted} style={{ marginLeft: spacing.sm }}>Transcription en cours…</Txt></View>}
            {error ? <Txt color={colors.error} size="sm" style={{ marginTop: spacing.md }}>{error}</Txt> : null}

            <Button testID="analyze-button" title="Analyser avec l'IA" icon="sparkles" loading={analyzing} onPress={analyze} style={{ marginTop: spacing.xl }} />
            {analyzing && <Txt color={colors.muted} size="sm" style={{ textAlign: "center", marginTop: spacing.md }}>L&apos;IA examine votre problème…</Txt>}
          </>
        )}

        {diag && (
          <>
            <View style={styles.resultHead}>
              <View style={styles.tradeIcon}><Ionicons name={diag.trade_icon as any} size={26} color={colors.brand} /></View>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <Txt weight="extrabold" size="xl">{diag.trade_label}</Txt>
                <View style={[styles.urgencyPill, { backgroundColor: (URGENCY_COLORS[diag.urgency] || colors.warning) + "33" }]}>
                  <View style={[styles.dot, { backgroundColor: URGENCY_COLORS[diag.urgency] || colors.warning }]} />
                  <Txt weight="semibold" size="sm" color={URGENCY_COLORS[diag.urgency] || colors.warning}>{URGENCY_LABELS[diag.urgency] || diag.urgency}</Txt>
                </View>
              </View>
            </View>

            <View style={styles.card}>
              <Txt color={colors.onSurfaceSecondary} style={{ lineHeight: 22 }}>{diag.problem}</Txt>
            </View>

            <View style={styles.statsGrid}>
              <Stat icon="time-outline" label="Durée estimée" value={`${diag.duration_min}–${diag.duration_max} h`} />
              <Stat icon="pricetag-outline" label="Prix estimé" value={`${diag.price_min}–${diag.price_max} €`} />
            </View>

            <View style={styles.card}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
                <Txt weight="semibold">Confiance de l&apos;IA</Txt>
                <Txt weight="bold" color={colors.brand}>{diag.confidence}%</Txt>
              </View>
              <View style={styles.gaugeBg}><View style={[styles.gaugeFill, { width: `${diag.confidence}%` }]} /></View>
            </View>

            {diag.causes?.length > 0 && (
              <View style={styles.card}>
                <Txt weight="semibold" style={{ marginBottom: spacing.sm }}>Causes possibles</Txt>
                {diag.causes.map((c, i) => (
                  <View key={i} style={styles.matRow}>
                    <Ionicons name="ellipse" size={7} color={colors.brand} style={{ marginTop: 6 }} />
                    <Txt color={colors.onSurfaceSecondary} style={{ marginLeft: spacing.sm, flex: 1 }}>{c}</Txt>
                  </View>
                ))}
              </View>
            )}

            {diag.materials?.length > 0 && (
              <View style={styles.card}>
                <Txt weight="semibold" style={{ marginBottom: spacing.sm }}>Matériel probable</Txt>
                {diag.materials.map((m, i) => (
                  <View key={i} style={styles.matRow}>
                    <Ionicons name="checkmark-circle" size={16} color={colors.brand} />
                    <Txt color={colors.onSurfaceSecondary} style={{ marginLeft: spacing.sm, flex: 1 }}>{m}</Txt>
                  </View>
                ))}
              </View>
            )}

            {diag.advice ? (
              <View style={[styles.card, { flexDirection: "row", alignItems: "flex-start", backgroundColor: colors.brand + "1A", borderColor: colors.brand + "55" }]}>
                <Ionicons name="shield-checkmark" size={18} color={colors.brand} />
                <Txt size="sm" color={colors.onSurface} style={{ marginLeft: spacing.sm, flex: 1 }}>{diag.advice}</Txt>
              </View>
            ) : null}

            {error ? <Txt color={colors.error} size="sm" style={{ marginTop: spacing.md }}>{error}</Txt> : null}

            <Button testID="find-pro-button" title="Trouver le meilleur pro" icon="navigate" loading={matching} onPress={findPro} style={{ marginTop: spacing.lg }} />
            <Pressable testID="restart-diag" onPress={() => { setDiag(null); setText(""); setImages([]); }} style={{ marginTop: spacing.md, alignItems: "center" }}>
              <Txt color={colors.muted} weight="semibold">Recommencer</Txt>
            </Pressable>
          </>
        )}
      </KeyboardAwareScrollView>
      {analyzing && <AIAnalyzing />}
    </View>
  );
}

function Tool({ icon, label, onPress, active, testID }: { icon: any; label: string; onPress: () => void; active?: boolean; testID: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={[styles.tool, active && { borderColor: colors.error, backgroundColor: colors.error + "1A" }]}>
      <Ionicons name={icon} size={22} color={active ? colors.error : colors.onSurface} />
      <Txt size="sm" weight="semibold" color={active ? colors.error : colors.onSurface} style={{ marginTop: 4 }}>{label}</Txt>
    </Pressable>
  );
}

function Stat({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={[styles.card, { flex: 1, marginBottom: 0 }]}>
      <Ionicons name={icon} size={18} color={colors.brand} />
      <Txt weight="bold" size="lg" style={{ marginTop: spacing.xs }}>{value}</Txt>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  textBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  textInput: { minHeight: 110, textAlignVertical: "top", fontFamily: font.medium, fontSize: fontSize.lg, color: colors.onSurface },
  thumbs: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  thumbWrap: { width: 80, height: 80 },
  thumb: { width: 80, height: 80, borderRadius: radius.md },
  thumbX: { position: "absolute", top: -6, right: -6, width: 22, height: 22, borderRadius: 11, backgroundColor: colors.error, alignItems: "center", justifyContent: "center" },
  toolRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  tool: { flex: 1, height: 72, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  inline: { flexDirection: "row", alignItems: "center", marginTop: spacing.md },
  resultHead: { flexDirection: "row", alignItems: "center", marginBottom: spacing.lg },
  tradeIcon: { width: 52, height: 52, borderRadius: radius.md, backgroundColor: colors.brand + "1A", alignItems: "center", justifyContent: "center" },
  urgencyPill: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill, marginTop: 4 },
  dot: { width: 6, height: 6, borderRadius: 3, marginRight: 6 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, marginBottom: spacing.md },
  statsGrid: { flexDirection: "row", gap: spacing.md, marginBottom: spacing.md },
  gaugeBg: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  gaugeFill: { height: 8, borderRadius: 4, backgroundColor: colors.brand },
  matRow: { flexDirection: "row", alignItems: "center", marginBottom: spacing.xs },
});
