/**
 * Intervention detail — client sees status of their instant request.
 * Polls every 4s until accepted/refused/cancelled.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, StyleSheet, Pressable, Alert, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeIn, FadeInUp, useSharedValue, useAnimatedStyle, withRepeat, withSequence, withTiming, Easing } from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import DepositPaymentSheet from "@/src/components/DepositPaymentSheet";

const COLORS = {
  bg: "#0B0B0B",
  bgSoft: "#141416",
  white: "#FFFFFF",
  accent: "#C8A96B",
  secondary: "#B8B8B8",
  muted: "#6E6E73",
  border: "#1F1F22",
  success: "#34D399",
  error: "#F87171",
};

type Intervention = {
  intervention_id: string;
  artisan_id: string;
  description: string;
  status: "pending" | "accepted" | "refused" | "cancelled" | "confirmed";
  created_at: string;
  accepted_at?: string;
  refused_at?: string;
  refuse_reason?: string;
  trade?: string;
  urgency?: string;
  deposit_status?: "pending" | "paid";
  deposit_amount_cents?: number;
};

function PulseRing() {
  const s = useSharedValue(1);
  const o = useSharedValue(0.6);
  useEffect(() => {
    s.value = withRepeat(withSequence(withTiming(1.6, { duration: 1400, easing: Easing.out(Easing.quad) }), withTiming(1, { duration: 0 })), -1, false);
    o.value = withRepeat(withSequence(withTiming(0, { duration: 1400 }), withTiming(0.6, { duration: 0 })), -1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const style = useAnimatedStyle(() => ({ transform: [{ scale: s.value }], opacity: o.value }));
  return <Animated.View style={[styles.pulse, style]} />;
}

export default function InterventionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id: string }>();
  const [iv, setIv] = useState<Intervention | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPay, setShowPay] = useState(false);
  const pollRef = useRef<any>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<Intervention>(`/interventions/${params.id}`);
      setIv(data);
      if (data.status === "accepted") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      } else if (data.status === "refused") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    load();
    pollRef.current = setInterval(() => {
      // Keep polling only while pending
      setIv((cur) => {
        if (cur && (cur.status === "confirmed" || cur.status === "refused" || cur.status === "cancelled")) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        } else {
          load();
        }
        return cur;
      });
    }, 4000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cancel = async () => {
    Alert.alert("Annuler la demande ?", "L'artisan ne pourra plus l'accepter.", [
      { text: "Non", style: "cancel" },
      {
        text: "Oui, annuler",
        style: "destructive",
        onPress: async () => {
          try {
            await api(`/interventions/${params.id}/cancel`, { method: "POST" });
            router.back();
          } catch (e: any) {
            Alert.alert("Erreur", e?.message);
          }
        },
      },
    ]);
  };

  if (loading || !iv) {
    return (
      <View style={styles.container}>
        <ActivityIndicator color={COLORS.accent} size="large" />
      </View>
    );
  }

  const needsDeposit = iv.status === "accepted" && iv.deposit_status !== "paid";
  const stateVisual = {
    pending: { icon: "time-outline", color: COLORS.accent, title: "En attente de réponse", sub: "L'artisan a été notifié — il répond en général en moins de 5 minutes." },
    accepted: {
      icon: "wallet-outline", color: COLORS.accent,
      title: "Demande acceptée !",
      sub: needsDeposit
        ? "Un petit acompte est requis pour confirmer et déclencher l'intervention."
        : "L'artisan est en route. Il vous contactera très bientôt.",
    },
    confirmed: { icon: "checkmark-circle", color: COLORS.success, title: "Intervention confirmée", sub: "L'artisan est en route. Il vous contactera très bientôt." },
    refused: { icon: "close-circle", color: COLORS.error, title: "Demande refusée", sub: iv.refuse_reason || "L'artisan n'est pas disponible pour le moment." },
    cancelled: { icon: "ban-outline", color: COLORS.muted, title: "Demande annulée", sub: "Vous avez annulé cette demande." },
  }[iv.status as keyof any] as { icon: string; color: string; title: string; sub: string };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.header}>
        <Pressable testID="back" onPress={() => router.replace("/")} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="close" size={22} color={COLORS.white} />
        </Pressable>
        <Txt weight="extrabold" size="base" style={{ color: COLORS.white }}>Intervention immédiate</Txt>
        <View style={{ width: 40 }} />
      </View>

      <Animated.View entering={FadeIn.duration(400)} style={styles.iconWrap}>
        {iv.status === "pending" && <PulseRing />}
        <View style={[styles.iconInner, { backgroundColor: `${stateVisual.color}22`, borderColor: `${stateVisual.color}66` }]}>
          <Ionicons name={stateVisual.icon as any} size={44} color={stateVisual.color} />
        </View>
      </Animated.View>

      <Animated.View entering={FadeInUp.delay(200).duration(500)} style={styles.center}>
        <Txt weight="extrabold" style={styles.title}>{stateVisual.title}</Txt>
        <Txt style={styles.subtitle}>{stateVisual.sub}</Txt>
      </Animated.View>

      <Animated.View entering={FadeInUp.delay(400).duration(500)} style={styles.card}>
        <View style={styles.row}>
          <Ionicons name="chatbubble-ellipses-outline" size={16} color={COLORS.muted} />
          <Txt size="sm" style={{ color: COLORS.secondary, marginLeft: 8, flex: 1 }} numberOfLines={3}>
            {iv.description}
          </Txt>
        </View>
        <View style={[styles.row, { marginTop: 10 }]}>
          <Ionicons name="build-outline" size={16} color={COLORS.muted} />
          <Txt size="sm" style={{ color: COLORS.secondary, marginLeft: 8 }}>
            {iv.trade || "—"}
          </Txt>
        </View>
      </Animated.View>

      <View style={{ flex: 1 }} />

      <View style={styles.actions}>
        {iv.status === "pending" && (
          <Pressable testID="cancel-btn" onPress={cancel} style={({ pressed }) => [styles.dangerBtn, pressed && { opacity: 0.7 }]}>
            <Txt weight="bold" style={{ color: COLORS.error }}>Annuler la demande</Txt>
          </Pressable>
        )}
        {needsDeposit && (
          <Pressable
            testID="pay-deposit-btn"
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
              setShowPay(true);
            }}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Ionicons name="wallet" size={18} color={COLORS.bg} />
            <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>
              Confirmer & payer l&apos;acompte
            </Txt>
          </Pressable>
        )}
        {(iv.status === "refused" || iv.status === "cancelled") && (
          <Pressable
            testID="retry"
            onPress={() => router.replace("/")}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Txt weight="bold" style={{ color: COLORS.bg }}>Retour à l&apos;accueil</Txt>
          </Pressable>
        )}
        {iv.status === "confirmed" && (
          <Pressable
            testID="view-pro"
            onPress={() => router.push({ pathname: "/artisan/[id]", params: { id: iv.artisan_id } })}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Txt weight="bold" style={{ color: COLORS.bg }}>Voir la fiche de l&apos;artisan</Txt>
          </Pressable>
        )}
      </View>

      <DepositPaymentSheet
        visible={showPay}
        interventionId={iv.intervention_id}
        onSuccess={() => {
          setShowPay(false);
          load();
        }}
        onCancel={() => setShowPay(false)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg, paddingHorizontal: 20 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 20 },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: COLORS.bgSoft,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  iconWrap: { alignItems: "center", justifyContent: "center", marginTop: 30, height: 140 },
  iconInner: {
    width: 100, height: 100, borderRadius: 50,
    borderWidth: 1,
    alignItems: "center", justifyContent: "center",
  },
  pulse: {
    position: "absolute",
    width: 100, height: 100, borderRadius: 50,
    backgroundColor: "rgba(200,169,107,0.25)",
  },
  center: { alignItems: "center", marginTop: 20, gap: 8 },
  title: { color: COLORS.white, fontSize: 22, textAlign: "center" },
  subtitle: { color: COLORS.secondary, fontSize: 14, textAlign: "center", lineHeight: 20, paddingHorizontal: 20 },
  card: {
    marginTop: 24,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 16,
    padding: 14,
    borderWidth: 1, borderColor: COLORS.border,
  },
  row: { flexDirection: "row", alignItems: "flex-start" },
  actions: { gap: 10 },
  primary: {
    backgroundColor: COLORS.accent,
    borderRadius: 18,
    paddingVertical: 16,
    alignItems: "center",
    justifyContent: "center",
  },
  dangerBtn: {
    borderRadius: 18,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: COLORS.error,
    backgroundColor: "rgba(248,113,113,0.06)",
  },
});
