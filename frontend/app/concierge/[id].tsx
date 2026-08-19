import { useEffect, useState, useCallback, useRef } from "react";
import { View, StyleSheet, ScrollView, TextInput, Pressable, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as DocumentPicker from "expo-document-picker";
import { AudioModule, useAudioRecorder } from "expo-audio";
import * as FileSystem from "expo-file-system";
import * as Haptics from "expo-haptics";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

type LiveDiagnosis = {
  issue: string;
  confidence: number;
  urgency: string;
  duration_min_hours?: number;
  duration_max_hours?: number;
  price_min_eur?: number;
  price_max_eur?: number;
  risks?: string[];
};
type Summary = {
  problem: string;
  trade: string;
  trade_label: string;
  urgency: string;
  duration_hours: string;
  price_range_eur: string;
  materials: string[];
  safety_advice: string;
  preparation_tips: string[];
  confidence: number;
};
type SafetyAlert = { level: string; message: string };
type ConciergeState = {
  ai_message: string;
  detected_trade: string | null;
  live_diagnosis: LiveDiagnosis;
  safety_alerts: SafetyAlert[];
  next_action: string;
  followup_suggestions: string[];
  summary: Summary | null;
};
type Turn = { role: "user" | "assistant" | "system"; text: string; ai_state?: ConciergeState; attachments?: any; created_at: string; video_placeholder?: boolean };

const URGENCY_COLORS: Record<string, string> = {
  faible: colors.success,
  moyenne: colors.warning,
  elevee: colors.warning,
  urgence: colors.error,
};

export default function ConciergeConversation() {
  const { id, mode } = useLocalSearchParams<{ id: string; mode?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);
  const audio = useAudioRecorder({ extension: ".m4a", sampleRate: 44100, numberOfChannels: 1, bitRate: 128000 } as any);

  const [sid, setSid] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [current, setCurrent] = useState<ConciergeState | null>(null);
  const [status, setStatus] = useState<string>("active");
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const [initializing, setInitializing] = useState(true);

  const bootstrap = useCallback(async () => {
    setInitializing(true);
    try {
      if (id === "new" || !id) {
        const res = await api<{ session_id: string; state: ConciergeState }>("/concierge/start", { method: "POST", body: {} });
        setSid(res.session_id);
        setCurrent(res.state);
        const initialTurns: Turn[] = [
          { role: "assistant", text: res.state.ai_message, ai_state: res.state, created_at: new Date().toISOString() },
        ];
        // FAQTOTUM V1 — Si l'utilisateur a explicitement demandé "urgence"
        // ou "planifié" depuis l'accueil, on injecte un system hint pour
        // que l'IA priorise ce contexte.
        if (mode === "urgent") {
          initialTurns.push({
            role: "system",
            text: "Vous avez choisi « Intervention immédiate ». Décrivez maintenant votre problème.",
            created_at: new Date().toISOString(),
          });
        } else if (mode === "schedule") {
          initialTurns.push({
            role: "system",
            text: "Vous avez choisi « Réserver un créneau ». Décrivez votre besoin, nous chercherons la meilleure disponibilité.",
            created_at: new Date().toISOString(),
          });
        }
        setTurns(initialTurns);
        router.setParams({ id: res.session_id });
      } else {
        const s = await api<any>(`/concierge/${id}`);
        setSid(s.session_id);
        setStatus(s.status || "active");
        setTurns(s.turns || []);
        const lastAi = [...(s.turns || [])].reverse().find((t: Turn) => t.role === "assistant" && t.ai_state);
        setCurrent(lastAi?.ai_state || null);
      }
    } catch {}
    setInitializing(false);
  }, [id, mode, router]);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  useEffect(() => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
  }, [turns]);

  const addAttachment = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return;
      const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, base64: true, quality: 0.6 });
      if (r.canceled || !r.assets?.[0]?.base64) return;
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      setAttachments((a) => [...a, `data:image/jpeg;base64,${r.assets[0].base64}`].slice(0, 4));
    } catch {}
  };

  const attachVideo = async () => {
    if (!sid) return;
    try {
      const r = await DocumentPicker.getDocumentAsync({ type: "video/*", copyToCacheDirectory: false });
      if (r.canceled || !r.assets?.[0]) return;
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
      await api(`/concierge/${sid}/video`, { method: "POST", body: { filename: r.assets[0].name, size_bytes: r.assets[0].size || 0 } });
      setTurns((t) => [...t, { role: "system", text: `Vidéo reçue (${r.assets[0].name}). L'analyse vidéo IA arrive bientôt.`, created_at: new Date().toISOString(), video_placeholder: true }]);
    } catch {}
  };

  const startVoice = async () => {
    try {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) return;
      await audio.prepareToRecordAsync();
      audio.record();
      setRecording(true);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    } catch {}
  };

  const stopVoice = async () => {
    setRecording(false);
    try {
      await audio.stop();
      const uri = audio.uri;
      if (!uri || !sid) return;
      const b64 = await FileSystem.readAsStringAsync(uri, { encoding: "base64" as any });
      setSending(true);
      const res = await api<{ state: ConciergeState; user_text: string }>(`/concierge/${sid}/message`, {
        method: "POST",
        body: { text: "", voice_base64: b64, voice_ext: "m4a" },
      });
      applyAiResponse(res, "🎙️");
    } catch {} finally { setSending(false); }
  };

  const applyAiResponse = (res: { state: ConciergeState; user_text?: string }, userPrefix = "") => {
    const userText = res.user_text || "";
    const userTurn: Turn = { role: "user", text: userText ? `${userPrefix ? userPrefix + " " : ""}${userText}` : userPrefix || "…", created_at: new Date().toISOString() };
    const aiTurn: Turn = { role: "assistant", text: res.state.ai_message, ai_state: res.state, created_at: new Date().toISOString() };
    setTurns((t) => [...t, userTurn, aiTurn]);
    setCurrent(res.state);
    if (res.state.next_action === "finish" || res.state.summary) setStatus("completed");
    Haptics.selectionAsync().catch(() => {});
  };

  const send = async (text?: string) => {
    if (!sid) return;
    const payload = text || input.trim();
    if (!payload && attachments.length === 0) return;
    setSending(true);
    const draftPhotos = [...attachments];
    setInput("");
    setAttachments([]);
    // Optimistic user turn
    setTurns((t) => [...t, { role: "user", text: payload || "(photos jointes)", attachments: { photos_count: draftPhotos.length }, created_at: new Date().toISOString() }]);
    try {
      const res = await api<{ state: ConciergeState }>(`/concierge/${sid}/message`, {
        method: "POST",
        body: { text: payload, photos_base64: draftPhotos.length ? draftPhotos : undefined },
      });
      const aiTurn: Turn = { role: "assistant", text: res.state.ai_message, ai_state: res.state, created_at: new Date().toISOString() };
      setTurns((t) => [...t, aiTurn]);
      setCurrent(res.state);
      if (res.state.next_action === "finish" || res.state.summary) setStatus("completed");
      Haptics.selectionAsync().catch(() => {});
    } catch { /* rollback? */ }
    setSending(false);
  };

  const finish = async () => {
    if (!sid) return;
    setSending(true);
    try {
      const res = await api<{ state: ConciergeState }>(`/concierge/${sid}/finish`, { method: "POST", body: {} });
      const aiTurn: Turn = { role: "assistant", text: res.state.ai_message, ai_state: res.state, created_at: new Date().toISOString() };
      setTurns((t) => [...t, aiTurn]);
      setCurrent(res.state);
      setStatus("completed");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch {}
    setSending(false);
  };

  const proceedToArtisan = () => {
    const trade = current?.summary?.trade || current?.detected_trade;
    if (!trade) return;
    router.push({ pathname: "/category/[slug]", params: { slug: trade } });
  };

  const startUrgentBroadcast = async () => {
    const sum = current?.summary;
    const trade = sum?.trade || current?.detected_trade;
    if (!trade) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    setSending(true);
    try {
      const now = new Date();
      const dateIso = now.toISOString().slice(0, 10);
      const hh = String((now.getHours() + 1) % 24).padStart(2, "0");
      // FAQTOTUM V1 — Extraction de l'estimation : d'abord depuis le summary
      // (source de vérité) puis fallback sur live_diagnosis courant.
      const priceMin =
        (sum as any)?.price_min_eur ?? current?.live_diagnosis?.price_min_eur;
      const priceMax =
        (sum as any)?.price_max_eur ?? current?.live_diagnosis?.price_max_eur;
      const bc = await api<{ broadcast_id: string; candidates_count: number }>(
        "/broadcasts",
        {
          method: "POST",
          body: {
            trade,
            date: dateIso,
            slot: `${hh}:00-${String((parseInt(hh, 10) + 2) % 24).padStart(2, "0")}:00`,
            description: sum?.problem || current?.live_diagnosis?.issue || "",
            urgent: true,
            estimated_price_min_eur: priceMin,
            estimated_price_max_eur: priceMax,
          },
        },
      );
      router.push({
        pathname: "/matching",
        params: { broadcast_id: bc.broadcast_id },
      });
    } catch (e) {
      router.push({ pathname: "/category/[slug]", params: { slug: trade } });
    } finally {
      setSending(false);
    }
  };

  if (initializing) {
    return <View style={{ flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" }}><ActivityIndicator color={colors.brand} /></View>;
  }

  const safetyAlerts = current?.safety_alerts || [];
  const ld = current?.live_diagnosis;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <View style={styles.auraDot} />
            <Txt weight="bold" size="lg" style={{ marginLeft: 6 }}>AURA</Txt>
          </View>
          <Txt size="sm" color={colors.muted}>{status === "completed" ? "Diagnostic finalisé" : "Concierge IA"}</Txt>
        </View>
        <Pressable testID="history-btn" onPress={() => router.push("/concierge")} style={styles.iconBtn}>
          <Ionicons name="time-outline" size={20} color={colors.onSurface} />
        </Pressable>
      </View>

      {/* Live diagnosis banner */}
      {ld && ld.confidence > 0 && (
        <View style={styles.liveCard}>
          <View style={{ flexDirection: "row", alignItems: "center" }}>
            <View style={styles.pulseIcon}>
              <Ionicons name="pulse" size={16} color={colors.brand} />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt size="sm" color={colors.muted} weight="semibold" style={{ letterSpacing: 0.5 }}>DIAGNOSTIC EN DIRECT</Txt>
              <Txt weight="bold" numberOfLines={2} style={{ marginTop: 2 }}>{ld.issue}</Txt>
            </View>
            <View style={[styles.urgencyChip, { backgroundColor: (URGENCY_COLORS[ld.urgency] || colors.muted) + "22", borderColor: (URGENCY_COLORS[ld.urgency] || colors.muted) + "55" }]}>
              <Txt size="sm" weight="bold" color={URGENCY_COLORS[ld.urgency] || colors.muted}>{ld.urgency}</Txt>
            </View>
          </View>
          <View style={styles.liveMetaRow}>
            <MetaCell label="Confiance" value={`${ld.confidence}%`} />
            <View style={styles.metaDivider} />
            <MetaCell label="Durée" value={ld.duration_min_hours ? `${ld.duration_min_hours}-${ld.duration_max_hours}h` : "—"} />
            <View style={styles.metaDivider} />
            <MetaCell label="Prix" value={ld.price_min_eur ? `${ld.price_min_eur}-${ld.price_max_eur}€` : "—"} />
          </View>
        </View>
      )}

      {/* Chat */}
      <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }} showsVerticalScrollIndicator={false}>
        {safetyAlerts.map((a, idx) => (
          <View key={idx} style={styles.safetyCard}>
            <Ionicons name="warning" size={18} color={colors.error} />
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold" size="sm" color={colors.error}>ALERTE SÉCURITÉ</Txt>
              <Txt size="sm" style={{ marginTop: 2, lineHeight: 20 }}>{a.message}</Txt>
            </View>
          </View>
        ))}

        {turns.map((t, i) => (
          <View key={i} style={[styles.bubble, t.role === "user" ? styles.bubbleUser : t.role === "system" ? styles.bubbleSystem : styles.bubbleAi]}>
            {t.role === "assistant" && (
              <View style={{ flexDirection: "row", alignItems: "center", marginBottom: 6 }}>
                <View style={styles.auraDot} />
                <Txt size="sm" color={colors.brand} weight="bold" style={{ marginLeft: 6 }}>AURA</Txt>
              </View>
            )}
            <Txt style={{ lineHeight: 22 }} color={t.role === "user" ? colors.onSurfaceInverse : colors.onSurface}>{t.text}</Txt>
            {t.attachments?.photos_count > 0 && (
              <Txt size="sm" color={t.role === "user" ? colors.onSurfaceInverse : colors.muted} style={{ marginTop: 4 }}>📎 {t.attachments.photos_count} photo{t.attachments.photos_count > 1 ? "s" : ""}</Txt>
            )}
          </View>
        ))}

        {/* Followup quick replies */}
        {status === "active" && current?.followup_suggestions && current.followup_suggestions.length > 0 && !sending && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.md }}>
            {current.followup_suggestions.map((s, i) => (
              <Pressable key={i} testID={`suggestion-${i}`} onPress={() => send(s)} style={styles.suggestion}>
                <Txt size="sm" color={colors.brand} weight="semibold">{s}</Txt>
              </Pressable>
            ))}
          </ScrollView>
        )}

        {sending && (
          <View style={[styles.bubble, styles.bubbleAi, { flexDirection: "row", alignItems: "center" }]}>
            <ActivityIndicator color={colors.brand} size="small" />
            <Txt color={colors.muted} style={{ marginLeft: spacing.sm }}>AURA réfléchit…</Txt>
          </View>
        )}

        {/* Final summary card */}
        {current?.summary && (
          <View style={styles.summaryCard}>
            <LinearGradient colors={[colors.brand + "22", colors.surfaceSecondary]} style={StyleSheet.absoluteFillObject as any} />
            <View style={{ flexDirection: "row", alignItems: "center", marginBottom: spacing.md }}>
              <Ionicons name="sparkles" size={22} color={colors.brand} />
              <Txt weight="extrabold" size="xl" style={{ marginLeft: spacing.sm }}>Diagnostic final</Txt>
            </View>
            <SummaryLine icon="alert-circle" label="Problème" value={current.summary.problem} />
            <SummaryLine icon="hammer" label="Métier" value={current.summary.trade_label} />
            <SummaryLine icon="time" label="Durée" value={current.summary.duration_hours} />
            <SummaryLine icon="pricetag" label="Budget" value={current.summary.price_range_eur} />
            <SummaryLine icon="flame" label="Urgence" value={current.summary.urgence || current.summary.urgency} />
            {current.summary.safety_advice && <SummaryLine icon="shield-checkmark" label="Sécurité" value={current.summary.safety_advice} />}
            {current.summary.preparation_tips?.length > 0 && (
              <View style={{ marginTop: spacing.md }}>
                <Txt size="sm" color={colors.muted} weight="semibold" style={{ letterSpacing: 0.5 }}>{"À PRÉPARER AVANT L'INTERVENTION"}</Txt>
                {current.summary.preparation_tips.map((tip, i) => (
                  <View key={i} style={{ flexDirection: "row", marginTop: 6 }}>
                    <Ionicons name="checkmark-circle" size={14} color={colors.success} />
                    <Txt size="sm" style={{ marginLeft: 6, flex: 1, lineHeight: 18 }} color={colors.onSurfaceSecondary}>{tip}</Txt>
                  </View>
                ))}
              </View>
            )}

            {/* FAQTOTUM V1 — Bloc ESTIMATION + CAUTION 7 %. */}
            {(() => {
              const s = current.summary as any;
              const priceMin = s.price_min_eur ?? current.live_diagnosis?.price_min_eur;
              const priceMax = s.price_max_eur ?? current.live_diagnosis?.price_max_eur;
              if (!priceMax) return null;
              const cautionCents = Math.round(priceMax * 100 * 0.07);
              const cautionEur = (cautionCents / 100).toFixed(2).replace(".", ",");
              const rangeText =
                priceMin && priceMin !== priceMax
                  ? `${priceMin} € — ${priceMax} €`
                  : `${priceMax} €`;
              return (
                <View testID="estimation-block" style={styles.estimationBlock}>
                  <Txt
                    weight="extrabold"
                    size="sm"
                    color={colors.textInverse}
                    style={{ letterSpacing: 1.5 }}
                  >
                    ESTIMATION FAQTOTUM
                  </Txt>
                  <Txt
                    weight="extrabold"
                    size="3xl"
                    color={colors.textInverse}
                    style={{ marginTop: 4 }}
                  >
                    {rangeText}
                  </Txt>
                  <Txt size="sm" color="#B4B4B4" style={{ marginTop: 4, lineHeight: 18 }}>
                    Estimation indicative. Le prix définitif est fixé par l&apos;artisan après diagnostic sur place.
                  </Txt>
                  <View style={styles.cautionRow}>
                    <View style={{ flex: 1 }}>
                      <Txt size="sm" color="#B4B4B4">
                        Caution (7 % de la borne haute)
                      </Txt>
                      <Txt
                        weight="extrabold"
                        size="xl"
                        color={colors.textInverse}
                        style={{ marginTop: 2 }}
                        testID="caution-amount"
                      >
                        {cautionEur} €
                      </Txt>
                    </View>
                    <Ionicons
                      name="shield-checkmark"
                      size={22}
                      color={colors.textInverse}
                    />
                  </View>
                </View>
              );
            })()}

            {/* FAQTOTUM V1 — Toujours 2 boutons finaux. Même si l'IA détecte
                l'urgence, le client garde le choix. */}
            <View style={styles.finalActions}>
              <Pressable
                testID="cta-urgent"
                onPress={startUrgentBroadcast}
                disabled={sending}
                style={({ pressed }) => [
                  styles.finalBtn,
                  styles.finalUrgent,
                  (pressed || sending) && { opacity: 0.85 },
                ]}
              >
                <Ionicons name="flash" size={18} color={colors.textInverse} />
                <View style={{ flex: 1, marginLeft: spacing.sm }}>
                  <Txt weight="extrabold" color={colors.textInverse}>
                    Intervention immédiate
                  </Txt>
                  <Txt size="sm" color="#FFCCCC" style={{ marginTop: 2 }}>
                    Trouver un artisan disponible maintenant
                  </Txt>
                </View>
              </Pressable>
              <Pressable
                testID="cta-schedule"
                onPress={proceedToArtisan}
                disabled={sending}
                style={({ pressed }) => [
                  styles.finalBtn,
                  styles.finalSchedule,
                  (pressed || sending) && { opacity: 0.85 },
                ]}
              >
                <Ionicons name="calendar" size={18} color={colors.textInverse} />
                <View style={{ flex: 1, marginLeft: spacing.sm }}>
                  <Txt weight="extrabold" color={colors.textInverse}>
                    Réserver un créneau
                  </Txt>
                  <Txt size="sm" color="#CCCCCC" style={{ marginTop: 2 }}>
                    Planifier à date choisie
                  </Txt>
                </View>
              </Pressable>
            </View>
          </View>
        )}
      </ScrollView>

      {/* Input bar */}
      {status === "active" && (
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={0}>
          {attachments.length > 0 && (
            <ScrollView horizontal contentContainerStyle={{ padding: spacing.sm, gap: spacing.sm }}>
              {attachments.map((a, i) => (
                <View key={i} style={styles.attachThumb}>
                  <Image source={{ uri: a }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
                  <Pressable onPress={() => setAttachments((prev) => prev.filter((_, j) => j !== i))} style={styles.attachRemove}>
                    <Ionicons name="close" size={12} color="#fff" />
                  </Pressable>
                </View>
              ))}
            </ScrollView>
          )}
          <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
            <Pressable testID="attach-photo" onPress={addAttachment} style={styles.actionBtn}>
              <Ionicons name="camera" size={20} color={colors.onSurface} />
            </Pressable>
            <Pressable testID="attach-video" onPress={attachVideo} style={styles.actionBtn}>
              <Ionicons name="videocam" size={20} color={colors.onSurface} />
            </Pressable>
            <TextInput
              testID="concierge-input"
              value={input}
              onChangeText={setInput}
              placeholder="Décrivez votre problème…"
              placeholderTextColor={colors.muted}
              multiline
              style={styles.input}
              onSubmitEditing={() => send()}
            />
            {input.trim().length > 0 || attachments.length > 0 ? (
              <Pressable testID="send-btn" onPress={() => send()} disabled={sending} style={[styles.sendBtn, { backgroundColor: colors.brand }]}>
                <Ionicons name="arrow-up" size={20} color={colors.onSurfaceInverse} />
              </Pressable>
            ) : (
              <Pressable
                testID="voice-btn"
                onPressIn={startVoice}
                onPressOut={stopVoice}
                style={[styles.sendBtn, { backgroundColor: recording ? colors.error : colors.surfaceSecondary, borderWidth: recording ? 0 : 1, borderColor: colors.border }]}
              >
                <Ionicons name={recording ? "stop" : "mic"} size={20} color={recording ? "#fff" : colors.onSurface} />
              </Pressable>
            )}
          </View>
          {turns.filter((t) => t.role === "user").length >= 2 && !current?.summary && (
            <Pressable testID="finish-btn" onPress={finish} disabled={sending} style={styles.finishRow}>
              <Ionicons name="checkmark-done" size={16} color={colors.brand} />
              <Txt size="sm" weight="bold" color={colors.brand} style={{ marginLeft: 6 }}>Terminer et voir le résumé</Txt>
            </Pressable>
          )}
        </KeyboardAvoidingView>
      )}
    </View>
  );
}

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, alignItems: "center" }}>
      <Txt weight="extrabold" size="lg">{value}</Txt>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
    </View>
  );
}
function SummaryLine({ icon, label, value }: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", marginBottom: spacing.sm }}>
      <Ionicons name={icon} size={16} color={colors.brand} style={{ marginTop: 2 }} />
      <View style={{ flex: 1, marginLeft: spacing.sm }}>
        <Txt size="sm" color={colors.muted}>{label}</Txt>
        <Txt weight="semibold" style={{ marginTop: 2, lineHeight: 20 }}>{value}</Txt>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  auraDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand },
  liveCard: { margin: spacing.lg, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.brand + "33" },
  pulseIcon: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.brand + "22", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brand + "55" },
  urgencyChip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  liveMetaRow: { flexDirection: "row", marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border },
  metaDivider: { width: 1, backgroundColor: colors.border, marginVertical: 4 },
  safetyCard: { flexDirection: "row", alignItems: "flex-start", padding: spacing.md, marginBottom: spacing.md, borderRadius: radius.md, backgroundColor: colors.error + "12", borderWidth: 1, borderColor: colors.error + "55" },
  bubble: { padding: spacing.md, borderRadius: radius.md, marginVertical: 4, maxWidth: "88%" },
  bubbleUser: { alignSelf: "flex-end", backgroundColor: colors.brand, borderBottomRightRadius: 4 },
  bubbleAi: { alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  bubbleSystem: { alignSelf: "center", backgroundColor: colors.brand + "0F", borderWidth: 1, borderColor: colors.brand + "33", borderStyle: "dashed" },
  suggestion: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brand + "14", borderWidth: 1, borderColor: colors.brand + "44", flexShrink: 0 },
  summaryCard: { marginTop: spacing.lg, padding: spacing.lg, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.brand + "55", overflow: "hidden" },
  inputBar: { flexDirection: "row", alignItems: "flex-end", padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm },
  actionBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  input: { flex: 1, minHeight: 40, maxHeight: 100, paddingHorizontal: spacing.md, paddingTop: 10, paddingBottom: 10, backgroundColor: colors.surfaceSecondary, borderRadius: 20, borderWidth: 1, borderColor: colors.border, color: colors.onSurface, fontFamily: font.medium, fontSize: fontSize.lg },
  sendBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  attachThumb: { width: 60, height: 60, borderRadius: radius.md, overflow: "hidden", position: "relative", borderWidth: 1, borderColor: colors.border },
  attachRemove: { position: "absolute", top: 2, right: 2, width: 18, height: 18, borderRadius: 9, backgroundColor: "rgba(0,0,0,0.7)", alignItems: "center", justifyContent: "center" },
  finishRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: spacing.sm, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  finalActions: { marginTop: spacing.lg, gap: spacing.sm },
  finalBtn: { flexDirection: "row", alignItems: "center", padding: spacing.lg, borderRadius: radius.md },
  finalUrgent: { backgroundColor: colors.error },
  finalSchedule: { backgroundColor: colors.brand },
  estimationBlock: { marginTop: spacing.lg, padding: spacing.lg, borderRadius: radius.md, backgroundColor: "#111111" },
  cautionRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.15)" },
});
