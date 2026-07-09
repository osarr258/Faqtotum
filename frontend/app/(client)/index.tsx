/**
 * Auxora — Helpo Home (ChatGPT-inspired AI-first experience)
 * ============================================================
 * The home screen IS the AI assistant.
 * User describes problem naturally → Helpo analyzes → suggests
 * top verified professionals — no manual trade selection.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import * as ImagePicker from "expo-image-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  withDelay,
  Easing,
  FadeIn,
  FadeInDown,
  FadeInUp,
} from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/AuthContext";

// ---------------- Design Tokens ----------------
const COLORS = {
  bg: "#0B0B0B",
  bgSoft: "#141416",
  white: "#FFFFFF",
  accent: "#C8A96B",
  accentSoft: "#D4BB86",
  secondary: "#B8B8B8",
  muted: "#6E6E73",
  border: "#1F1F22",
  glass: "rgba(255,255,255,0.04)",
};

const PROMPTS = [
  "Ma chaudière fuit…",
  "Ma porte d'entrée ne s'ouvre plus…",
  "Je n'ai plus d'électricité…",
  "Ma clim ne refroidit plus…",
  "Je veux rénover ma salle de bain…",
  "Mon toit fuit…",
];

type Diagnosis = {
  problem: string;
  trade: string;
  trade_label: string;
  urgency: string;
  duration_min: number;
  duration_max: number;
  price_min: number;
  price_max: number;
  causes?: string[];
  advice?: string;
  confidence?: number;
};

type Artisan = {
  artisan_id: string;
  name: string;
  title: string;
  city: string;
  hourly_rate: number;
  rating: number;
  reviews_count: number;
  photo?: string;
  trade_name: string;
  identity_verified?: boolean;
  insurance_verified?: boolean;
  avg_arrival_min?: number;
  available?: boolean;
};

// ---------------- Sub-components ----------------

/** Animated cursor blink */
function BlinkingCursor() {
  const opacity = useSharedValue(1);
  useEffect(() => {
    opacity.value = withRepeat(
      withSequence(withTiming(0, { duration: 500 }), withTiming(1, { duration: 500 })),
      -1,
      false,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));
  return <Animated.View style={[styles.cursor, style]} />;
}

/** Rotating placeholder text (like ChatGPT). */
function RotatingPlaceholder({ visible }: { visible: boolean }) {
  const [idx, setIdx] = useState(0);
  const opacity = useSharedValue(1);
  const ty = useSharedValue(0);

  useEffect(() => {
    if (!visible) return;
    const iv = setInterval(() => {
      opacity.value = withTiming(0, { duration: 250 });
      ty.value = withTiming(-6, { duration: 250 });
      setTimeout(() => {
        setIdx((i) => (i + 1) % PROMPTS.length);
        ty.value = 6;
        opacity.value = withTiming(1, { duration: 300, easing: Easing.out(Easing.cubic) });
        ty.value = withTiming(0, { duration: 300, easing: Easing.out(Easing.cubic) });
      }, 260);
    }, 2600);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: ty.value }],
  }));

  if (!visible) return null;

  return (
    <View style={styles.placeholderWrap} pointerEvents="none">
      <Animated.View style={style}>
        <Txt size="base" color={COLORS.muted} style={styles.placeholderText}>
          {PROMPTS[idx]}
        </Txt>
      </Animated.View>
      <BlinkingCursor />
    </View>
  );
}

/** Typing dots for "Helpo is thinking…" */
function TypingDots() {
  const d1 = useSharedValue(0.3);
  const d2 = useSharedValue(0.3);
  const d3 = useSharedValue(0.3);
  useEffect(() => {
    const opts = { duration: 480, easing: Easing.inOut(Easing.ease) };
    d1.value = withRepeat(withSequence(withTiming(1, opts), withTiming(0.3, opts)), -1, false);
    d2.value = withDelay(160, withRepeat(withSequence(withTiming(1, opts), withTiming(0.3, opts)), -1, false));
    d3.value = withDelay(320, withRepeat(withSequence(withTiming(1, opts), withTiming(0.3, opts)), -1, false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const s1 = useAnimatedStyle(() => ({ opacity: d1.value }));
  const s2 = useAnimatedStyle(() => ({ opacity: d2.value }));
  const s3 = useAnimatedStyle(() => ({ opacity: d3.value }));
  return (
    <View style={styles.dotsRow}>
      <Animated.View style={[styles.dot, s1]} />
      <Animated.View style={[styles.dot, s2]} />
      <Animated.View style={[styles.dot, s3]} />
    </View>
  );
}

/** Ambient glow around Helpo halo */
function HelpoGlow() {
  const scale = useSharedValue(1);
  const opacity = useSharedValue(0.5);
  useEffect(() => {
    scale.value = withRepeat(
      withSequence(
        withTiming(1.15, { duration: 2400, easing: Easing.inOut(Easing.quad) }),
        withTiming(1, { duration: 2400, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      true,
    );
    opacity.value = withRepeat(
      withSequence(
        withTiming(0.75, { duration: 2400, easing: Easing.inOut(Easing.quad) }),
        withTiming(0.45, { duration: 2400, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      true,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const style = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));
  return <Animated.View pointerEvents="none" style={[styles.helpoGlow, style]} />;
}

// ---------------- Main Screen ----------------
export default function HelpoHome() {
  const router = useRouter();
  const { user } = useAuth();
  const firstName = (user?.name || "").split(" ")[0];
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);

  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [pros, setPros] = useState<Artisan[]>([]);
  const [loadingPros, setLoadingPros] = useState(false);
  const [showPros, setShowPros] = useState(false);

  const hasText = text.trim().length > 0;
  const canAnalyze = hasText || images.length > 0;

  const focus = () => {};

  const analyze = async (emergency = false) => {
    if (!canAnalyze) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setAnalyzing(true);
    setDiag(null);
    setPros([]);
    setShowPros(false);
    try {
      const finalText = emergency ? `[URGENCE] ${text}` : text;
      const result = await api<Diagnosis>("/ai/diagnose", {
        method: "POST",
        body: { text: finalText, images },
      });
      setDiag(result);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 300);
    } catch (e: any) {
      Alert.alert("Auxora", e?.message || "Impossible d'analyser. Réessayez.");
    } finally {
      setAnalyzing(false);
    }
  };

  const loadPros = useCallback(async () => {
    if (!diag) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setLoadingPros(true);
    setShowPros(true);
    try {
      const list = await api<Artisan[]>(`/artisans?category=${encodeURIComponent(diag.trade)}`, {
        auth: false,
      });
      setPros(list.slice(0, 6));
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 200);
    } finally {
      setLoadingPros(false);
    }
  }, [diag]);

  const pickImage = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm.status !== "granted") {
      Alert.alert("Permission", "Accès à la photothèque requis.");
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"] as any,
      base64: true,
      quality: 0.6,
      allowsMultipleSelection: false,
    });
    if (!res.canceled && res.assets?.[0]?.base64) {
      setImages((prev) => [...prev, `data:image/jpeg;base64,${res.assets[0].base64}`]);
    }
  };

  const voiceMessage = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    router.push({ pathname: "/concierge/[id]", params: { id: "new" } });
  };

  const emergency = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    if (!hasText && images.length === 0) {
      setText("URGENCE : ");
      return;
    }
    analyze(true);
  };

  const openArtisan = (a: Artisan) => {
    Haptics.selectionAsync().catch(() => {});
    router.push({ pathname: "/artisan/[id]", params: { id: a.artisan_id } });
  };

  const resetConversation = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setText("");
    setImages([]);
    setDiag(null);
    setPros([]);
    setShowPros(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: COLORS.bg }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={0}
      >
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={{
            paddingTop: insets.top + 8,
            paddingBottom: insets.bottom + 120,
          }}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Ambient background glow */}
          <View pointerEvents="none" style={styles.bgGlow}>
            <LinearGradient
              colors={["rgba(200,169,107,0.14)", "transparent"]}
              start={{ x: 0.5, y: 0 }}
              end={{ x: 0.5, y: 1 }}
              style={StyleSheet.absoluteFillObject as any}
            />
          </View>

          {/* Header */}
          <Animated.View entering={FadeIn.duration(500)} style={styles.topBar}>
            <View style={styles.brandRow}>
              <View style={styles.brandDot} />
              <Txt weight="extrabold" size="sm" style={styles.brandText}>AUXORA</Txt>
            </View>
            {!!diag && (
              <Pressable testID="new-chat" onPress={resetConversation} hitSlop={12} style={styles.newChatBtn}>
                <Ionicons name="add" size={18} color={COLORS.white} />
              </Pressable>
            )}
          </Animated.View>

          {/* Auxora hero */}
          <Animated.View entering={FadeInDown.delay(100).duration(600)} style={styles.hero}>
            <View style={styles.helpoAvatarWrap}>
              <HelpoGlow />
              <View style={styles.helpoAvatar}>
                <Ionicons name="sparkles" size={26} color={COLORS.accent} />
              </View>
            </View>
            <Txt weight="extrabold" style={styles.helpoName}>
              {firstName ? `Comment puis-je vous aider ${firstName} ?` : "Comment puis-je vous aider ?"}
            </Txt>
          </Animated.View>

          {/* Conversation */}
          {(analyzing || diag) && (
            <View style={styles.chatWrap}>
              {/* User bubble */}
              <Animated.View entering={FadeInUp.duration(400)} style={styles.userBubble}>
                <Txt size="base" style={{ color: COLORS.white, lineHeight: 22 }}>
                  {text}
                </Txt>
                {images.length > 0 && (
                  <View style={{ flexDirection: "row", gap: 6, marginTop: 8 }}>
                    {images.map((im, i) => (
                      <Image key={i} source={{ uri: im }} style={styles.chatThumb} contentFit="cover" />
                    ))}
                  </View>
                )}
              </Animated.View>

              {/* AI bubble */}
              <Animated.View entering={FadeInUp.delay(300).duration(500)} style={styles.aiBubble}>
                <View style={styles.aiHeader}>
                  <View style={styles.aiAvatarSmall}>
                    <Ionicons name="sparkles" size={12} color={COLORS.accent} />
                  </View>
                  <Txt weight="semibold" size="sm" color={COLORS.secondary}>Auxora</Txt>
                </View>

                {analyzing && <TypingDots />}

                {!!diag && (
                  <View>
                    <Txt size="base" style={styles.aiText}>
                      J&apos;ai analysé votre demande.
                    </Txt>
                    <Txt size="base" style={[styles.aiText, { marginTop: 8 }]}>
                      Il s&apos;agit d&apos;un problème lié à{" "}
                      <Txt weight="bold" color={COLORS.accent}>{diag.trade_label}</Txt>
                      {diag.urgency === "urgence" || diag.urgency === "elevee" ? (
                        <>
                          {" "}
                          <Txt weight="bold" color="#FF6B6B">— urgence détectée</Txt>
                        </>
                      ) : null}
                      .
                    </Txt>
                    {!!diag.advice && (
                      <View style={styles.adviceBox}>
                        <Ionicons name="shield-checkmark" size={14} color={COLORS.accent} />
                        <Txt size="sm" style={{ flex: 1, marginLeft: 8, color: COLORS.secondary, lineHeight: 20 }}>
                          {diag.advice}
                        </Txt>
                      </View>
                    )}
                    <View style={styles.metaRow}>
                      <Meta icon="time-outline" label={`${diag.duration_min}-${diag.duration_max} h`} />
                      <Meta icon="cash-outline" label={`${diag.price_min}-${diag.price_max} €`} />
                      {diag.confidence != null && (
                        <Meta icon="analytics-outline" label={`${diag.confidence}%`} />
                      )}
                    </View>
                    <Txt size="base" style={[styles.aiText, { marginTop: 12 }]}>
                      Voulez-vous voir les meilleurs {diag.trade_label.toLowerCase()}s vérifiés près de chez vous ?
                    </Txt>
                    {!showPros && (
                      <Pressable
                        testID="view-pros-btn"
                        onPress={loadPros}
                        style={({ pressed }) => [styles.viewProsBtn, pressed && { opacity: 0.85 }]}
                      >
                        <Txt weight="bold" color={COLORS.bg}>Voir les professionnels</Txt>
                        <Ionicons name="arrow-forward" size={16} color={COLORS.bg} style={{ marginLeft: 6 }} />
                      </Pressable>
                    )}
                  </View>
                )}
              </Animated.View>

              {/* Pros */}
              {showPros && (
                <View style={{ marginTop: 20, gap: 12 }}>
                  {loadingPros && (
                    <View style={{ paddingVertical: 24, alignItems: "center" }}>
                      <ActivityIndicator color={COLORS.accent} />
                    </View>
                  )}
                  {!loadingPros && pros.length === 0 && (
                    <View style={styles.emptyPros}>
                      <Ionicons name="search-outline" size={22} color={COLORS.muted} />
                      <Txt style={{ marginTop: 8, color: COLORS.secondary, textAlign: "center" }}>
                        Aucun {diag?.trade_label.toLowerCase()} disponible pour le moment.
                      </Txt>
                    </View>
                  )}
                  {!loadingPros &&
                    pros.map((a, i) => (
                      <Animated.View key={a.artisan_id} entering={FadeInUp.delay(i * 80).duration(400)}>
                        <ProCard artisan={a} onPress={() => openArtisan(a)} />
                      </Animated.View>
                    ))}
                </View>
              )}
            </View>
          )}
        </ScrollView>

        {/* Sticky bottom input area */}
        <View style={[styles.dockWrap, { paddingBottom: insets.bottom + 12 }]}>
          {Platform.OS !== "web" ? (
            <BlurView intensity={40} tint="dark" style={StyleSheet.absoluteFillObject} pointerEvents="none" />
          ) : (
            <View style={[StyleSheet.absoluteFillObject, { backgroundColor: "rgba(11,11,11,0.85)" }]} pointerEvents="none" />
          )}
          <LinearGradient
            colors={["rgba(11,11,11,0)", "rgba(11,11,11,0.98)"]}
            style={styles.dockTopFade}
            pointerEvents="none"
          />

          {/* Image thumbnails */}
          {images.length > 0 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }}>
              {images.map((im, i) => (
                <View key={i} style={styles.thumbWrap}>
                  <Image source={{ uri: im }} style={styles.thumb} contentFit="cover" />
                  <Pressable
                    onPress={() => setImages((p) => p.filter((_, idx) => idx !== i))}
                    style={styles.thumbRemove}
                    hitSlop={8}
                  >
                    <Ionicons name="close" size={12} color={COLORS.white} />
                  </Pressable>
                </View>
              ))}
            </ScrollView>
          )}

          {/* Input container */}
          <View style={styles.inputContainer}>
            <View style={styles.inputRow}>
              <TextInput
                testID="helpo-input"
                value={text}
                onChangeText={setText}
                onFocus={focus}
                multiline
                maxLength={800}
                style={styles.input}
                placeholder=""
                placeholderTextColor="transparent"
              />
              <RotatingPlaceholder visible={!text} />
            </View>

            <View style={styles.actionsRow}>
              <ActionBtn icon="camera-outline" label="Photo" onPress={pickImage} />
              <ActionBtn icon="mic-outline" label="Voix" onPress={voiceMessage} />
              <ActionBtn icon="flash-outline" label="Urgence" onPress={emergency} tone="danger" />
              <View style={{ flex: 1 }} />
              <Pressable
                testID="analyze-btn"
                disabled={!canAnalyze || analyzing}
                onPress={() => analyze(false)}
                style={({ pressed }) => [
                  styles.sendBtn,
                  (!canAnalyze || analyzing) && { opacity: 0.4 },
                  pressed && { transform: [{ scale: 0.96 }] },
                ]}
              >
                {analyzing ? (
                  <ActivityIndicator size="small" color={COLORS.bg} />
                ) : (
                  <Ionicons name="arrow-up" size={20} color={COLORS.bg} />
                )}
              </Pressable>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

// ---------------- Small components ----------------

function Meta({ icon, label }: { icon: any; label: string }) {
  return (
    <View style={styles.meta}>
      <Ionicons name={icon} size={13} color={COLORS.secondary} />
      <Txt size="sm" style={{ marginLeft: 4, color: COLORS.secondary }}>{label}</Txt>
    </View>
  );
}

function ActionBtn({
  icon,
  label,
  onPress,
  tone,
}: {
  icon: any;
  label: string;
  onPress: () => void;
  tone?: "danger";
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.actionBtn, pressed && { opacity: 0.65 }]}>
      <Ionicons name={icon} size={16} color={tone === "danger" ? "#FF6B6B" : COLORS.white} />
      <Txt size="sm" weight="semibold" style={{ marginLeft: 5, color: tone === "danger" ? "#FF6B6B" : COLORS.white }}>
        {label}
      </Txt>
    </Pressable>
  );
}

function ProCard({ artisan, onPress }: { artisan: Artisan; onPress: () => void }) {
  const arrival = artisan.avg_arrival_min ? `${artisan.avg_arrival_min} min` : "Aujourd'hui";
  return (
    <Pressable
      testID={`pro-${artisan.artisan_id}`}
      onPress={onPress}
      style={({ pressed }) => [styles.proCard, pressed && { transform: [{ scale: 0.985 }] }]}
    >
      <View style={styles.proPhotoWrap}>
        {artisan.photo ? (
          <Image source={{ uri: artisan.photo }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
        ) : (
          <View style={[styles.proPhotoWrap, { alignItems: "center", justifyContent: "center", backgroundColor: COLORS.bgSoft }]}>
            <Ionicons name="person" size={28} color={COLORS.muted} />
          </View>
        )}
        {artisan.identity_verified && (
          <View style={styles.verifBadge}>
            <Ionicons name="checkmark" size={9} color={COLORS.bg} />
          </View>
        )}
      </View>
      <View style={{ flex: 1, marginLeft: 14 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Txt weight="bold" size="base" color={COLORS.white} numberOfLines={1} style={{ flex: 1 }}>
            {artisan.name}
          </Txt>
          <View style={styles.ratingChip}>
            <Ionicons name="star" size={11} color={COLORS.accent} />
            <Txt size="sm" weight="bold" color={COLORS.white} style={{ marginLeft: 3 }}>{artisan.rating.toFixed(1)}</Txt>
          </View>
        </View>
        <Txt size="sm" color={COLORS.secondary} numberOfLines={1} style={{ marginTop: 2 }}>
          {artisan.trade_name} · {artisan.city}
        </Txt>
        <View style={styles.proMetaRow}>
          <View style={styles.proMeta}>
            <Ionicons name="time-outline" size={11} color={COLORS.muted} />
            <Txt size="sm" style={{ marginLeft: 3, color: COLORS.muted }}>{arrival}</Txt>
          </View>
          <View style={styles.proMeta}>
            <Ionicons name="cash-outline" size={11} color={COLORS.muted} />
            <Txt size="sm" style={{ marginLeft: 3, color: COLORS.muted }}>{artisan.hourly_rate}€/h</Txt>
          </View>
          {artisan.available && (
            <View style={[styles.proMeta, { backgroundColor: "rgba(52,211,153,0.12)", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }]}>
              <View style={styles.dotGreen} />
              <Txt size="sm" style={{ marginLeft: 4, color: "#34D399" }}>Dispo</Txt>
            </View>
          )}
        </View>
      </View>
      <Ionicons name="chevron-forward" size={18} color={COLORS.muted} />
    </Pressable>
  );
}

// ---------------- Styles ----------------
const styles = StyleSheet.create({
  bgGlow: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 500,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingBottom: 4,
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  brandDot: {
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: COLORS.accent,
    shadowColor: COLORS.accent, shadowOpacity: 1, shadowRadius: 6, shadowOffset: { width: 0, height: 0 },
  },
  brandText: { color: COLORS.white, letterSpacing: 4 },
  newChatBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: COLORS.glass,
    borderWidth: 1, borderColor: COLORS.border,
    alignItems: "center", justifyContent: "center",
  },

  hero: { alignItems: "center", paddingHorizontal: 24, paddingTop: 28, paddingBottom: 20 },
  helpoAvatarWrap: {
    width: 76, height: 76,
    alignItems: "center", justifyContent: "center",
    marginBottom: 14,
  },
  helpoGlow: {
    position: "absolute",
    width: 76, height: 76, borderRadius: 38,
    backgroundColor: "rgba(200,169,107,0.28)",
    shadowColor: COLORS.accent, shadowOpacity: 0.9, shadowRadius: 30, shadowOffset: { width: 0, height: 0 },
  },
  helpoAvatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: COLORS.bgSoft,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.4)",
    alignItems: "center", justifyContent: "center",
  },
  helpoName: {
    color: COLORS.white,
    fontSize: 30,
    letterSpacing: -0.5,
    lineHeight: 38,
    textAlign: "center",
    paddingHorizontal: 8,
  },
  helpoTagline: {
    color: COLORS.secondary,
    fontSize: 14,
    marginTop: 6,
    textAlign: "center",
  },
  helpoIntro: {
    color: COLORS.muted,
    fontSize: 13,
    marginTop: 20,
    textAlign: "center",
    lineHeight: 20,
  },

  // Chat
  chatWrap: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 24,
    gap: 12,
  },
  userBubble: {
    alignSelf: "flex-end",
    maxWidth: "88%",
    backgroundColor: COLORS.bgSoft,
    paddingHorizontal: 16, paddingVertical: 12,
    borderRadius: 22,
    borderTopRightRadius: 6,
    borderWidth: 1, borderColor: COLORS.border,
  },
  aiBubble: {
    alignSelf: "flex-start",
    maxWidth: "94%",
    backgroundColor: "rgba(200,169,107,0.05)",
    paddingHorizontal: 18, paddingVertical: 16,
    borderRadius: 22,
    borderTopLeftRadius: 6,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.15)",
  },
  aiHeader: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 10 },
  aiAvatarSmall: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: "rgba(200,169,107,0.15)",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: "rgba(200,169,107,0.35)",
  },
  aiText: { color: COLORS.white, lineHeight: 22 },
  adviceBox: {
    flexDirection: "row", alignItems: "flex-start",
    marginTop: 12,
    padding: 12,
    backgroundColor: COLORS.glass,
    borderRadius: 12,
    borderWidth: 1, borderColor: COLORS.border,
  },
  metaRow: { flexDirection: "row", gap: 10, marginTop: 14, flexWrap: "wrap" },
  meta: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 10, paddingVertical: 6,
    backgroundColor: COLORS.glass,
    borderRadius: 10,
    borderWidth: 1, borderColor: COLORS.border,
  },
  viewProsBtn: {
    flexDirection: "row",
    alignItems: "center", justifyContent: "center",
    backgroundColor: COLORS.accent,
    borderRadius: 14,
    paddingVertical: 14,
    marginTop: 16,
  },

  chatThumb: { width: 60, height: 60, borderRadius: 10 },

  // Dots
  dotsRow: { flexDirection: "row", gap: 6, paddingVertical: 4 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: COLORS.accent },

  // Trust
  trustSection: { paddingHorizontal: 20, marginTop: 8, marginBottom: 24 },
  trustHeader: { color: COLORS.muted, letterSpacing: 1.4, marginBottom: 12 },
  trustRow: { flexDirection: "row", gap: 10 },
  trustCard: {
    flex: 1,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 18,
    padding: 14,
    borderWidth: 1, borderColor: COLORS.border,
    minHeight: 120,
  },
  trustIcon: {
    width: 36, height: 36, borderRadius: 12,
    backgroundColor: "rgba(200,169,107,0.12)",
    alignItems: "center", justifyContent: "center",
  },

  // Dock (bottom input)
  dockWrap: {
    position: "absolute", bottom: 0, left: 0, right: 0,
    paddingHorizontal: 16,
    paddingTop: 20,
    overflow: "visible",
  },
  dockTopFade: {
    position: "absolute", left: 0, right: 0, top: -40, height: 40,
  },
  inputContainer: {
    backgroundColor: COLORS.bgSoft,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: COLORS.border,
    paddingHorizontal: 18,
    paddingTop: 14,
    paddingBottom: 10,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.5,
    shadowRadius: 24,
    elevation: 12,
  },
  inputRow: { minHeight: 30, justifyContent: "center" },
  placeholderWrap: {
    position: "absolute",
    left: 0,
    top: 6,
    flexDirection: "row",
    alignItems: "center",
    pointerEvents: "none",
  },
  placeholderText: {
    color: COLORS.muted,
    fontSize: 15,
  },
  cursor: {
    width: 2, height: 16, backgroundColor: COLORS.accent, marginLeft: 3, borderRadius: 1,
  },
  input: {
    color: COLORS.white,
    fontSize: 16,
    minHeight: 30,
    maxHeight: 120,
    padding: 0,
    lineHeight: 22,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 12,
    gap: 8,
  },
  actionBtn: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10, paddingVertical: 8,
    backgroundColor: COLORS.glass,
    borderRadius: 12,
    borderWidth: 1, borderColor: COLORS.border,
  },
  sendBtn: {
    width: 38, height: 38, borderRadius: 19,
    backgroundColor: COLORS.accent,
    alignItems: "center", justifyContent: "center",
  },

  // Thumbnails
  thumbWrap: { marginRight: 8 },
  thumb: { width: 56, height: 56, borderRadius: 12 },
  thumbRemove: {
    position: "absolute", top: -4, right: -4,
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: "rgba(0,0,0,0.85)",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },

  // Pros
  proCard: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: COLORS.bgSoft,
    borderRadius: 20,
    padding: 12,
    borderWidth: 1, borderColor: COLORS.border,
  },
  proPhotoWrap: {
    width: 64, height: 64, borderRadius: 32,
    overflow: "hidden",
    backgroundColor: COLORS.bgSoft,
  },
  verifBadge: {
    position: "absolute", bottom: 0, right: 0,
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: COLORS.accent,
    alignItems: "center", justifyContent: "center",
    borderWidth: 2, borderColor: COLORS.bgSoft,
  },
  ratingChip: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 8, paddingVertical: 3,
    backgroundColor: "rgba(200,169,107,0.12)",
    borderRadius: 8,
  },
  proMetaRow: { flexDirection: "row", gap: 12, marginTop: 8, alignItems: "center" },
  proMeta: { flexDirection: "row", alignItems: "center" },
  dotGreen: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#34D399" },
  emptyPros: {
    alignItems: "center",
    padding: 20,
    borderRadius: 16,
    backgroundColor: COLORS.bgSoft,
    borderWidth: 1, borderColor: COLORS.border,
  },
});
