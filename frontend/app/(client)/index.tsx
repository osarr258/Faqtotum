/**
 * Faqtotum V1 — Accueil Client (AI-first).
 *
 * Le point d'entrée central de l'expérience client. L'IA est le pivot :
 * une zone héro "Décrivez ce qui vous arrive…" ouvre la conversation
 * concierge (route existante `/concierge`). Sous le héro :
 *   - 2 actions rapides (Intervention immédiate / Réserver un créneau)
 *   - Historique des 3 dernières réservations avec statut
 *   - Bandeau réassurance (artisans vérifiés)
 *
 * Design : monochrome noir/blanc/gris FAQTOTUM. Aucun gradient.
 * Aucune fonctionnalité mockée — l'appui "Décrivez…" ouvre la vraie
 * session concierge côté backend.
 */
import { useCallback, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Pressable,
  RefreshControl,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar } from "@/src/components/ui";
import FaqtotumLogo from "@/src/components/FaqtotumLogo";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Booking = {
  booking_id: string;
  artisan_name?: string;
  trade_name?: string;
  date: string;
  slot: string;
  status: string;
  urgent?: boolean;
};

const STATUS_LABEL: Record<string, string> = {
  pending: "En attente",
  accepted: "Confirmée",
  confirmed: "Confirmée",
  professional_on_the_way: "En route",
  en_route: "En route",
  arrived: "Sur place",
  in_progress: "En cours",
  awaiting_validation: "À valider",
  completed: "Terminée",
  declined: "Refusée",
  cancelled: "Annulée",
};

const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  pending: { bg: colors.surfaceSecondary, fg: colors.onSurface },
  accepted: { bg: colors.brand, fg: colors.textInverse },
  confirmed: { bg: colors.brand, fg: colors.textInverse },
  en_route: { bg: colors.brand, fg: colors.textInverse },
  professional_on_the_way: { bg: colors.brand, fg: colors.textInverse },
  arrived: { bg: colors.brand, fg: colors.textInverse },
  in_progress: { bg: colors.brand, fg: colors.textInverse },
  awaiting_validation: { bg: colors.warning, fg: "#442200" },
  completed: { bg: "#D1FAE5", fg: "#065F46" },
  declined: { bg: colors.surfaceSecondary, fg: colors.muted },
  cancelled: { bg: colors.surfaceSecondary, fg: colors.muted },
};

export default function ClientHome() {
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await api<Booking[]>("/bookings/mine").catch(() => []);
      setBookings(list || []);
    } catch {
      /* silent */
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const openConcierge = async (mode: "text" | "urgent" | "schedule" = "text") => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    if (mode === "schedule") {
      router.push("/reserve");
      return;
    }
    router.push({
      pathname: "/concierge/[id]",
      params: { id: "new", ...(mode !== "text" ? { mode } : {}) },
    });
  };

  const firstName = (user?.name || "").split(" ")[0] || "";
  const hour = new Date().getHours();
  const greeting =
    hour < 6
      ? "Bonne nuit"
      : hour < 12
        ? "Bonjour"
        : hour < 18
          ? "Bon après-midi"
          : "Bonsoir";

  const recent = bookings
    .filter((b) => b.status !== "cancelled")
    .slice(0, 3);

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + 100,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.brand}
          />
        }
      >
        {/* --- Header ------------------------------------------------ */}
        <View style={styles.header}>
          <View style={styles.brandBlock}>
            <FaqtotumLogo size={32} color={colors.brand} />
            <View style={{ marginLeft: 10 }}>
              <Txt
                weight="extrabold"
                size="lg"
                style={{ letterSpacing: -0.3, lineHeight: 20 }}
              >
                faqtotum
              </Txt>
              <Txt
                size="sm"
                color={colors.muted}
                style={{ letterSpacing: 0.5, marginTop: -2 }}
              >
                votre expert du quotidien
              </Txt>
            </View>
            <View style={{ flex: 1 }} />
            <Pressable
              testID="header-avatar"
              onPress={() => router.push("/(client)/profile")}
              hitSlop={10}
            >
              <Avatar name={user?.name} size={40} />
            </Pressable>
          </View>
          <View style={{ marginTop: spacing.xl }}>
            <Txt size="sm" color={colors.muted}>
              {greeting},
            </Txt>
            <Txt
              weight="extrabold"
              size="3xl"
              style={{ marginTop: 2, letterSpacing: -0.5 }}
            >
              {firstName || "Client"}
            </Txt>
          </View>
        </View>

        {/* --- HERO IA — le vrai point d'entrée -------------------- */}
        <Pressable
          testID="hero-ai-input"
          onPress={() => openConcierge("text")}
          style={({ pressed }) => [
            styles.aiHero,
            pressed && { opacity: 0.92 },
          ]}
        >
          <View style={styles.aiTitleRow}>
            <View style={styles.aiSparkle}>
              <Ionicons name="sparkles" size={16} color={colors.textInverse} />
            </View>
            <Txt weight="extrabold" size="lg" color={colors.textInverse}>
              Que puis-je faire pour vous ?
            </Txt>
          </View>
          <Txt
            size="base"
            color="#CFCFCF"
            style={{ marginTop: 6, lineHeight: 22 }}
          >
            {'"Ma chaudière ne fonctionne plus depuis ce matin."'}
          </Txt>
          <Txt
            size="sm"
            color="#8A8A8A"
            style={{ marginTop: spacing.md, lineHeight: 20 }}
          >
            Décrivez librement votre problème. L&apos;IA vous propose l&apos;artisan
            adapté en quelques secondes.
          </Txt>
          <View style={styles.aiFooter}>
            <View style={styles.aiChip}>
              <Ionicons
                name="mic-outline"
                size={14}
                color={colors.textInverse}
              />
              <Txt
                size="sm"
                color={colors.textInverse}
                style={{ marginLeft: 6 }}
              >
                Voix
              </Txt>
            </View>
            <View style={styles.aiChip}>
              <Ionicons
                name="camera-outline"
                size={14}
                color={colors.textInverse}
              />
              <Txt
                size="sm"
                color={colors.textInverse}
                style={{ marginLeft: 6 }}
              >
                Photo
              </Txt>
            </View>
            <View style={{ flex: 1 }} />
            <View style={styles.aiStart}>
              <Txt
                weight="bold"
                size="sm"
                color={colors.brand}
                style={{ marginRight: 6 }}
              >
                Commencer
              </Txt>
              <Ionicons name="arrow-forward" size={16} color={colors.brand} />
            </View>
          </View>
        </Pressable>

        {/* --- Quick actions ---------------------------------------- */}
        <View style={styles.quickRow}>
          <Pressable
            testID="quick-urgent"
            onPress={() => openConcierge("urgent")}
            style={({ pressed }) => [
              styles.quickCard,
              styles.quickUrgent,
              pressed && { opacity: 0.92 },
            ]}
          >
            <View style={styles.quickIconUrgent}>
              <Ionicons name="flash" size={22} color={colors.textInverse} />
            </View>
            <Txt weight="extrabold" size="base" style={{ marginTop: spacing.md }}>
              Intervention immédiate
            </Txt>
            <Txt
              size="sm"
              color={colors.muted}
              style={{ marginTop: 4, lineHeight: 18 }}
            >
              Trouver un artisan disponible maintenant
            </Txt>
          </Pressable>
          <Pressable
            testID="quick-schedule"
            onPress={() => openConcierge("schedule")}
            style={({ pressed }) => [
              styles.quickCard,
              pressed && { opacity: 0.92 },
            ]}
          >
            <View style={styles.quickIcon}>
              <Ionicons name="calendar" size={20} color={colors.textInverse} />
            </View>
            <Txt weight="extrabold" size="base" style={{ marginTop: spacing.md }}>
              Réserver un créneau
            </Txt>
            <Txt
              size="sm"
              color={colors.muted}
              style={{ marginTop: 4, lineHeight: 18 }}
            >
              Planifier une intervention à date choisie
            </Txt>
          </Pressable>
        </View>

        {/* --- Recent bookings -------------------------------------- */}
        {recent.length > 0 && (
          <View style={styles.section}>
            <View style={styles.sectionHead}>
              <Txt weight="bold" size="lg">
                Mes demandes récentes
              </Txt>
              <Pressable
                testID="see-all-bookings"
                onPress={() => router.push("/(client)/bookings")}
                hitSlop={10}
              >
                <Txt weight="bold" size="sm" color={colors.brand}>
                  Voir tout
                </Txt>
              </Pressable>
            </View>
            {recent.map((b) => (
              <Pressable
                key={b.booking_id}
                testID={`recent-${b.booking_id}`}
                onPress={() =>
                  router.push({
                    pathname: "/track/[id]",
                    params: { id: b.booking_id },
                  })
                }
                style={({ pressed }) => [
                  styles.bkCard,
                  b.urgent && { borderColor: colors.error, borderWidth: 1.5 },
                  pressed && { opacity: 0.9 },
                ]}
              >
                <View style={styles.bkIcon}>
                  <Ionicons
                    name="briefcase-outline"
                    size={18}
                    color={colors.onSurface}
                  />
                </View>
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <View
                    style={{
                      flexDirection: "row",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <Txt weight="bold">
                      {b.artisan_name || "Artisan"}
                    </Txt>
                    {b.urgent ? (
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
                  </View>
                  <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                    {b.date} · {b.slot}
                  </Txt>
                </View>
                <View
                  style={[
                    styles.statusPill,
                    {
                      backgroundColor:
                        STATUS_STYLE[b.status]?.bg || colors.surfaceSecondary,
                    },
                  ]}
                >
                  <Txt
                    weight="bold"
                    size="sm"
                    color={STATUS_STYLE[b.status]?.fg || colors.onSurface}
                  >
                    {STATUS_LABEL[b.status] || b.status}
                  </Txt>
                </View>
              </Pressable>
            ))}
          </View>
        )}

        {/* --- Reassurance ------------------------------------------ */}
        <View style={styles.trustBox}>
          <View style={styles.trustIcon}>
            <Ionicons
              name="shield-checkmark"
              size={22}
              color={colors.textInverse}
            />
          </View>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="bold" size="sm">
              Artisans vérifiés
            </Txt>
            <Txt
              size="sm"
              color={colors.muted}
              style={{ marginTop: 2, lineHeight: 18 }}
            >
              Identité, assurance, SIRET contrôlés. Paiement sécurisé Stripe.
            </Txt>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  header: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.lg,
  },
  brandBlock: {
    flexDirection: "row",
    alignItems: "center",
  },
  logoRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.lg,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  aiHero: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: "#111111",
  },
  aiTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  aiSparkle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center",
  },
  aiFooter: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.lg,
    gap: spacing.sm,
  },
  aiChip: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: "rgba(255,255,255,0.10)",
  },
  aiStart: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.textInverse,
  },
  quickRow: {
    flexDirection: "row",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing["2xl"],
  },
  quickCard: {
    flex: 1,
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  quickUrgent: {
    borderColor: colors.error,
    borderWidth: 1.5,
  },
  quickIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  quickIconUrgent: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
  },
  section: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing["2xl"],
  },
  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.md,
  },
  bkCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
  },
  bkIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  statusPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    marginLeft: spacing.sm,
  },
  urgentTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
    backgroundColor: colors.error,
  },
  trustBox: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
  trustIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
});
