/**
 * Artisan Hub — FAQTOTUM v1
 *
 * Écran d'atterrissage de l'espace artisan. Structure claire, monochrome,
 * hiérarchie éditoriale forte :
 *
 *   1. En-tête : logo P + salutation + avatar
 *   2. Bandeau vérification (si profil incomplet)
 *   3. Zone URGENT (si demande urgente en attente) — badge pulsant
 *   4. Nouvelles demandes (max 3)
 *   5. Aujourd'hui (interventions du jour)
 *   6. Stats compactes (note, missions, temps de réponse)
 *
 * Cet écran ne dépend d'AUCUN nouvel endpoint backend — il consomme
 * `/bookings/received` et `/artisans/me` déjà existants. La liste complète
 * des missions ira dans (artisan)/missions.tsx à l'étape #2.
 */
import { useCallback, useMemo, useState } from "react";
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
import RequestCard, { RequestData } from "@/src/components/RequestCard";
import UrgentBanner from "@/src/components/UrgentBanner";
import { useUrgentAlert } from "@/src/hooks/useUrgentAlert";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Booking = RequestData & {
  conversation_id?: string;
  reviewed?: boolean;
};

type ArtisanProfile = {
  trade?: string;
  title?: string;
  bio?: string;
  city?: string;
  phone?: string;
  rating?: number;
  jobs_done?: number;
  response_min?: number;
  verified?: boolean;
  verification_status?: string;
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ArtisanHub() {
  const { user } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [profile, setProfile] = useState<ArtisanProfile | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const { alert: urgentAlert, dismiss: dismissAlert } = useUrgentAlert({
    intervalMs: 8000,
  });

  const load = useCallback(async () => {
    try {
      const [bk, pf] = await Promise.all([
        api<Booking[]>("/bookings/received").catch(() => []),
        api<ArtisanProfile | null>("/artisans/me").catch(() => null),
      ]);
      setBookings(bk || []);
      setProfile(pf);
    } finally {
      setLoading(false);
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

  const setStatus = async (id: string, status: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    try {
      await api(`/bookings/${id}`, { method: "PATCH", body: { status } });
      load();
    } catch {
      /* silent */
    }
  };

  const pending = useMemo(
    () => bookings.filter((b) => b.status === "pending"),
    [bookings],
  );
  const urgentPending = useMemo(
    () => pending.filter((b) => b.urgent),
    [pending],
  );
  const accepted = useMemo(
    () => bookings.filter((b) => b.status === "accepted"),
    [bookings],
  );
  const today = useMemo(() => {
    const iso = todayIso();
    return accepted.filter((b) => b.date === iso);
  }, [accepted]);
  const completed = useMemo(
    () => bookings.filter((b) => b.status === "completed"),
    [bookings],
  );

  const isProfileComplete = !!(
    profile &&
    profile.trade &&
    profile.title &&
    (profile.bio || "").length > 20
  );

  const firstName = (user?.name || "").split(" ")[0] || "artisan";
  const hour = new Date().getHours();
  const greeting =
    hour < 6
      ? "Bonne nuit"
      : hour < 12
        ? "Bonjour"
        : hour < 18
          ? "Bon après-midi"
          : "Bonsoir";

  return (
    <View style={styles.root}>
      <UrgentBanner
        visible={!!urgentAlert}
        onPress={() => {
          if (urgentAlert) {
            router.push({
              pathname: "/track/[id]",
              params: { id: urgentAlert.bookingId },
            });
            dismissAlert();
          }
        }}
        onDismiss={dismissAlert}
      />
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + spacing["3xl"],
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.brand}
          />
        }
      >
        {/* --- Header -------------------------------------------------- */}
        <View style={styles.header}>
          <View style={styles.logoRow}>
            <FaqtotumLogo size={24} color={colors.brand} />
            <Txt
              weight="bold"
              size="sm"
              style={{ marginLeft: 8, letterSpacing: 0.5 }}
            >
              faqtotum
            </Txt>
          </View>
          <View style={styles.headerRow}>
            <View style={{ flex: 1 }}>
              <Txt size="sm" color={colors.muted}>
                {greeting},
              </Txt>
              <Txt weight="extrabold" size="3xl" style={{ marginTop: 2 }}>
                {firstName}
              </Txt>
            </View>
            <Pressable
              testID="header-avatar"
              onPress={() => router.push("/(artisan)/profile")}
              hitSlop={10}
            >
              <Avatar name={user?.name} size={44} />
            </Pressable>
          </View>
        </View>

        {/* --- Verification banner ------------------------------------- */}
        {!isProfileComplete && (
          <Pressable
            testID="verification-banner"
            onPress={() => router.push("/(artisan)/profile")}
            style={({ pressed }) => [
              styles.verifBanner,
              pressed && { opacity: 0.85 },
            ]}
          >
            <View style={styles.verifDot} />
            <View style={{ flex: 1 }}>
              <Txt weight="bold" size="sm">
                Profil incomplet
              </Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                Complétez votre profil pour être visible auprès des clients.
              </Txt>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        )}

        {/* --- Urgent zone --------------------------------------------- */}
        {urgentPending.length > 0 && (
          <View style={styles.section}>
            <View style={styles.sectionHead}>
              <View style={styles.urgentTag}>
                <View style={styles.urgentDotStatic} />
                <Txt
                  weight="extrabold"
                  size="sm"
                  color={colors.textInverse}
                  style={{ letterSpacing: 1.5 }}
                >
                  URGENT
                </Txt>
              </View>
              <Txt weight="bold" size="lg" style={{ marginLeft: spacing.sm }}>
                {urgentPending.length} demande
                {urgentPending.length > 1 ? "s" : ""} prioritaire
                {urgentPending.length > 1 ? "s" : ""}
              </Txt>
            </View>
            {urgentPending.slice(0, 2).map((b) => (
              <RequestCard
                key={b.booking_id}
                request={b}
                onAccept={(id) => setStatus(id, "accepted")}
                onDecline={(id) => setStatus(id, "declined")}
                onOpen={(id) =>
                  router.push({
                    pathname: "/track/[id]",
                    params: { id },
                  })
                }
              />
            ))}
          </View>
        )}

        {/* --- New requests -------------------------------------------- */}
        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Txt weight="bold" size="lg">
              Nouvelles demandes
            </Txt>
            {pending.length > 0 && (
              <View style={styles.pill}>
                <Txt
                  weight="bold"
                  size="sm"
                  color={colors.textInverse}
                >
                  {pending.length}
                </Txt>
              </View>
            )}
          </View>
          {loading ? (
            <View style={styles.skeleton} />
          ) : pending.length === 0 ? (
            <View style={styles.emptyCard}>
              <Ionicons
                name="mail-open-outline"
                size={22}
                color={colors.muted}
              />
              <Txt size="sm" color={colors.muted} style={{ marginTop: 8 }}>
                Aucune nouvelle demande. Restez disponible pour en recevoir.
              </Txt>
            </View>
          ) : (
            <>
              {pending
                .filter((b) => !b.urgent)
                .slice(0, 3)
                .map((b) => (
                  <RequestCard
                    key={b.booking_id}
                    request={b}
                    onAccept={(id) => setStatus(id, "accepted")}
                    onDecline={(id) => setStatus(id, "declined")}
                    onOpen={(id) =>
                      router.push({
                        pathname: "/track/[id]",
                        params: { id },
                      })
                    }
                    compact
                  />
                ))}
              {pending.length > 3 && (
                <Pressable
                  testID="see-all-requests"
                  onPress={() => router.push("/(artisan)/live")}
                  style={styles.seeAll}
                >
                  <Txt weight="bold" size="sm">
                    Voir toutes les demandes ({pending.length})
                  </Txt>
                  <Ionicons name="arrow-forward" size={16} color={colors.brand} />
                </Pressable>
              )}
            </>
          )}
        </View>

        {/* --- Today --------------------------------------------------- */}
        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Txt weight="bold" size="lg">
              {"Aujourd'hui"}
            </Txt>
            {today.length > 0 && (
              <Txt size="sm" color={colors.muted} style={{ marginLeft: 8 }}>
                {today.length} intervention{today.length > 1 ? "s" : ""}
              </Txt>
            )}
          </View>
          {today.length === 0 ? (
            <View style={styles.emptyCard}>
              <Ionicons name="calendar-outline" size={22} color={colors.muted} />
              <Txt size="sm" color={colors.muted} style={{ marginTop: 8 }}>
                {"Aucune intervention prévue aujourd'hui."}
              </Txt>
            </View>
          ) : (
            today.map((b) => (
              <Pressable
                key={b.booking_id}
                testID={`today-${b.booking_id}`}
                onPress={() =>
                  router.push({
                    pathname: "/track/[id]",
                    params: { id: b.booking_id },
                  })
                }
                style={({ pressed }) => [
                  styles.todayCard,
                  pressed && { opacity: 0.9 },
                ]}
              >
                <View style={styles.todayTimeBox}>
                  <Txt weight="extrabold" size="lg">
                    {b.slot.split("-")[0] || b.slot}
                  </Txt>
                </View>
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <Txt weight="bold">{b.client_name}</Txt>
                  {b.trade_name ? (
                    <Txt size="sm" color={colors.muted}>
                      {b.trade_name}
                    </Txt>
                  ) : null}
                </View>
                <Ionicons
                  name="chevron-forward"
                  size={18}
                  color={colors.muted}
                />
              </Pressable>
            ))
          )}
        </View>

        {/* --- Stats --------------------------------------------------- */}
        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Txt weight="bold" size="lg">
              Ma performance
            </Txt>
          </View>
          <View style={styles.statsRow}>
            <View style={styles.statBox}>
              <Ionicons name="star" size={16} color={colors.brand} />
              <Txt weight="extrabold" size="2xl" style={{ marginTop: 6 }}>
                {profile?.rating ? profile.rating.toFixed(1) : "—"}
              </Txt>
              <Txt size="sm" color={colors.muted}>
                Note
              </Txt>
            </View>
            <View style={styles.statBox}>
              <Ionicons name="briefcase" size={16} color={colors.brand} />
              <Txt weight="extrabold" size="2xl" style={{ marginTop: 6 }}>
                {(profile?.jobs_done ?? 0) + completed.length}
              </Txt>
              <Txt size="sm" color={colors.muted}>
                Missions
              </Txt>
            </View>
            <View style={styles.statBox}>
              <Ionicons name="time-outline" size={16} color={colors.brand} />
              <Txt weight="extrabold" size="2xl" style={{ marginTop: 6 }}>
                {profile?.response_min ? `${profile.response_min}m` : "—"}
              </Txt>
              <Txt size="sm" color={colors.muted}>
                Réponse
              </Txt>
            </View>
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
  logoRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.lg,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  verifBanner: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    marginBottom: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    gap: spacing.md,
  },
  verifDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.warning,
  },
  section: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing["2xl"],
  },
  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
  },
  pill: {
    marginLeft: 8,
    backgroundColor: colors.brand,
    paddingHorizontal: 8,
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  urgentTag: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.error,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.sm,
    gap: 6,
  },
  urgentDotStatic: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.textInverse,
  },
  emptyCard: {
    padding: spacing.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    backgroundColor: colors.surface,
  },
  skeleton: {
    height: 120,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
  },
  seeAll: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.md,
    gap: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
  todayCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
  },
  todayTimeBox: {
    width: 64,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  statsRow: {
    flexDirection: "row",
    gap: spacing.md,
  },
  statBox: {
    flex: 1,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "flex-start",
    backgroundColor: colors.surface,
  },
});
