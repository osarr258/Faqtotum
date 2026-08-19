/**
 * Broadcast Status — FAQTOTUM V1
 *
 * Écran client qui suit un broadcast en temps réel après que l'IA a
 * proposé "Intervention immédiate".
 *
 * Cycle :
 *   1. Recherche      — broadcast open, on poll toutes les 4 s
 *   2. Artisan trouvé — dès que winner_booking_id apparaît → redirect /track
 *   3. Expiration     — status="expired" après 30 min (urgent) / 60 min (normal)
 *
 * Aucune donnée sensible sur les candidats — juste `candidates_count`.
 * L'utilisateur peut annuler ("cancel") ou basculer vers un créneau si
 * personne n'accepte.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  StyleSheet,
  Pressable,
  Alert,
  ActivityIndicator,
  Animated,
  Easing,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import FaqtotumLogo from "@/src/components/FaqtotumLogo";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Broadcast = {
  broadcast_id: string;
  trade?: string;
  date?: string;
  slot?: string;
  description?: string;
  urgent?: boolean;
  status: "open" | "assigned" | "expired" | "cancelled";
  candidates_count?: number;
  winner_booking_id?: string | null;
  estimated_price_min_eur?: number | null;
  estimated_price_max_eur?: number | null;
  caution_eur_display?: string;
  created_at?: string;
  expires_at?: string;
};

const POLL_MS = 4000;

export default function BroadcastStatus() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [bc, setBc] = useState<Broadcast | null>(null);
  const [loading, setLoading] = useState(true);
  const [elapsedSec, setElapsedSec] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const spin = useRef(new Animated.Value(0)).current;

  // Rotation loop du cercle de recherche.
  useEffect(() => {
    Animated.loop(
      Animated.timing(spin, {
        toValue: 1,
        duration: 2200,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    ).start();
  }, [spin]);

  const rotate = spin.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "360deg"],
  });

  const fetchBc = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api<Broadcast>(`/broadcasts/${id}`);
      setBc(data);
      if (data.status === "assigned" && data.winner_booking_id) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(
          () => {},
        );
        // Stop timers & redirect.
        if (pollRef.current) clearInterval(pollRef.current);
        if (timerRef.current) clearInterval(timerRef.current);
        router.replace({
          pathname: "/track/[id]",
          params: { id: data.winner_booking_id },
        });
      }
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [id, router]);

  useEffect(() => {
    fetchBc();
    pollRef.current = setInterval(fetchBc, POLL_MS);
    timerRef.current = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchBc]);

  const cancel = async () => {
    if (!bc) return;
    Alert.alert(
      "Annuler la demande",
      "Souhaitez-vous vraiment annuler votre demande ?",
      [
        { text: "Non", style: "cancel" },
        {
          text: "Oui, annuler",
          style: "destructive",
          onPress: async () => {
            try {
              await api(`/broadcasts/${bc.broadcast_id}/cancel`, {
                method: "POST",
              });
              router.replace("/(client)");
            } catch (e) {
              const s = e instanceof Error ? e.message : "Erreur";
              Alert.alert("Erreur", s);
            }
          },
        },
      ],
    );
  };

  if (loading || !bc) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} size="large" />
      </View>
    );
  }

  const isExpired = bc.status === "expired";
  const isCancelled = bc.status === "cancelled";
  const isOpen = bc.status === "open";
  const mm = String(Math.floor(elapsedSec / 60)).padStart(2, "0");
  const ss = String(elapsedSec % 60).padStart(2, "0");

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View
        style={[styles.header, { paddingTop: insets.top + spacing.md }]}
      >
        <Pressable
          testID="close-btn"
          onPress={() => router.replace("/(client)")}
          style={styles.iconBtn}
          hitSlop={10}
        >
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={styles.logoRow}>
          <FaqtotumLogo size={20} color={colors.brand} />
          <Txt weight="bold" size="sm" style={{ marginLeft: 6 }}>
            faqtotum
          </Txt>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <View style={{ flex: 1, paddingHorizontal: spacing.lg }}>
        {/* --- HERO cercle animé -------------------------------- */}
        <View style={styles.hero}>
          {isOpen ? (
            <>
              <View style={styles.spinnerWrap}>
                <Animated.View
                  style={[
                    styles.spinnerRing,
                    { transform: [{ rotate }] },
                  ]}
                />
                <View style={styles.spinnerCenter}>
                  <Ionicons name="sparkles" size={30} color={colors.brand} />
                </View>
              </View>
              <Txt
                weight="extrabold"
                size="2xl"
                style={{ marginTop: spacing.xl, textAlign: "center" }}
              >
                Recherche d&apos;un artisan…
              </Txt>
              <Txt
                size="base"
                color={colors.muted}
                style={{
                  marginTop: spacing.sm,
                  textAlign: "center",
                  lineHeight: 22,
                }}
              >
                Nous contactons {bc.candidates_count || 0} artisan
                {(bc.candidates_count || 0) > 1 ? "s" : ""} qualifié
                {(bc.candidates_count || 0) > 1 ? "s" : ""}. Le premier qui
                accepte gagne la mission.
              </Txt>
              <View style={styles.timerRow}>
                <Ionicons name="time-outline" size={14} color={colors.muted} />
                <Txt
                  size="sm"
                  color={colors.muted}
                  style={{ marginLeft: 6 }}
                >
                  {mm}:{ss}
                </Txt>
              </View>
            </>
          ) : isExpired ? (
            <>
              <View style={[styles.spinnerCenter, styles.warningIcon]}>
                <Ionicons name="time" size={30} color={colors.textInverse} />
              </View>
              <Txt
                weight="extrabold"
                size="2xl"
                style={{ marginTop: spacing.xl, textAlign: "center" }}
              >
                Aucun artisan disponible
              </Txt>
              <Txt
                size="base"
                color={colors.muted}
                style={{
                  marginTop: spacing.sm,
                  textAlign: "center",
                  lineHeight: 22,
                }}
              >
                Personne n&apos;a pu répondre dans les temps. Vous pouvez
                réserver un créneau plus tard.
              </Txt>
            </>
          ) : isCancelled ? (
            <>
              <View style={[styles.spinnerCenter, styles.cancelIcon]}>
                <Ionicons name="close" size={30} color={colors.textInverse} />
              </View>
              <Txt
                weight="extrabold"
                size="2xl"
                style={{ marginTop: spacing.xl, textAlign: "center" }}
              >
                Demande annulée
              </Txt>
            </>
          ) : null}
        </View>

        {/* --- Récap demande ------------------------------------ */}
        <View style={styles.card}>
          <Txt
            weight="bold"
            size="sm"
            color={colors.muted}
            style={{ letterSpacing: 1, marginBottom: spacing.sm }}
          >
            VOTRE DEMANDE
          </Txt>
          {bc.description ? (
            <Txt style={{ lineHeight: 22 }}>{bc.description}</Txt>
          ) : (
            <Txt color={colors.muted}>Sans description</Txt>
          )}
          <View style={styles.metaRow}>
            {bc.urgent ? (
              <View style={styles.urgentTag}>
                <Txt
                  weight="extrabold"
                  size="sm"
                  color={colors.textInverse}
                  style={{ letterSpacing: 1 }}
                >
                  URGENT
                </Txt>
              </View>
            ) : null}
            {bc.trade ? (
              <View style={styles.tradeChip}>
                <Ionicons name="briefcase" size={12} color={colors.onSurface} />
                <Txt weight="bold" size="sm" style={{ marginLeft: 6 }}>
                  {bc.trade}
                </Txt>
              </View>
            ) : null}
          </View>
          {bc.estimated_price_max_eur ? (
            <View style={styles.estimBox}>
              <View style={{ flex: 1 }}>
                <Txt size="sm" color={colors.muted}>
                  Estimation
                </Txt>
                <Txt weight="extrabold" size="lg" style={{ marginTop: 2 }}>
                  {bc.estimated_price_min_eur
                    ? `${bc.estimated_price_min_eur} € — ${bc.estimated_price_max_eur} €`
                    : `${bc.estimated_price_max_eur} €`}
                </Txt>
              </View>
              {bc.caution_eur_display ? (
                <View style={{ alignItems: "flex-end" }}>
                  <Txt size="sm" color={colors.muted}>
                    Caution 7 %
                  </Txt>
                  <Txt weight="extrabold" size="lg" style={{ marginTop: 2 }}>
                    {bc.caution_eur_display}
                  </Txt>
                </View>
              ) : null}
            </View>
          ) : null}
        </View>

        {/* --- Actions ------------------------------------------- */}
        <View style={styles.actions}>
          {isOpen ? (
            <Pressable
              testID="cancel-broadcast"
              onPress={cancel}
              style={({ pressed }) => [
                styles.cancelBtn,
                pressed && { opacity: 0.85 },
              ]}
            >
              <Txt weight="bold" color={colors.error}>
                Annuler la demande
              </Txt>
            </Pressable>
          ) : (
            <Button
              testID="back-home"
              title="Retour à l&apos;accueil"
              onPress={() => router.replace("/(client)")}
            />
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  logoRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  hero: {
    alignItems: "center",
    paddingVertical: spacing["2xl"],
  },
  spinnerWrap: {
    width: 140,
    height: 140,
    alignItems: "center",
    justifyContent: "center",
  },
  spinnerRing: {
    position: "absolute",
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 4,
    borderColor: colors.surfaceSecondary,
    borderTopColor: colors.brand,
    borderRightColor: colors.brand,
  },
  spinnerCenter: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  warningIcon: {
    backgroundColor: colors.warning,
  },
  cancelIcon: {
    backgroundColor: colors.muted,
  },
  timerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.md,
  },
  card: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.md,
  },
  metaRow: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.md,
    alignItems: "center",
  },
  urgentTag: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.sm,
    backgroundColor: colors.error,
  },
  tradeChip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  estimBox: {
    marginTop: spacing.md,
    flexDirection: "row",
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
  actions: {
    marginTop: spacing.lg,
  },
  cancelBtn: {
    alignItems: "center",
    justifyContent: "center",
    height: 52,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
});
