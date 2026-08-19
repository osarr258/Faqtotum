/**
 * Artisan Missions — FAQTOTUM v1
 *
 * Remplace l'ancien écran "Live" hérité. Structure claire :
 *
 *   1. Header (titre + toggle "Disponible maintenant" — essentiel matching)
 *   2. Segment control : À traiter / En cours / Historique
 *   3. Liste des missions unifiées (bookings + interventions) selon segment
 *
 * Le nom de la route reste "live" pour l'instant (renommage au step 3).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Pressable,
  Switch,
  Alert,
  RefreshControl,
  ActivityIndicator,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import RequestCard from "@/src/components/RequestCard";
import MissionCard, { MissionData } from "@/src/components/MissionCard";
import UrgentBanner from "@/src/components/UrgentBanner";
import { useUrgentAlert } from "@/src/hooks/useUrgentAlert";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type Booking = {
  booking_id: string;
  conversation_id?: string;
  client_name: string;
  trade_name?: string;
  date: string;
  slot: string;
  description?: string;
  status: string;
  urgent?: boolean;
};

type Intervention = {
  intervention_id: string;
  client_name?: string;
  description?: string;
  status: string;
  urgency?: string;
  trade?: string;
  total_amount_cents?: number;
  balance_cents?: number;
  created_at?: string;
};

type Segment = "todo" | "active" | "history";

const SEGMENTS: { key: Segment; label: string }[] = [
  { key: "todo", label: "À traiter" },
  { key: "active", label: "En cours" },
  { key: "history", label: "Historique" },
];

const TODO_STATUSES = new Set([
  "pending",
  "requested",
  "assigned",
]);
const ACTIVE_STATUSES = new Set([
  "accepted",
  "confirmed",
  "professional_on_the_way",
  "en_route",
  "arrived",
  "in_progress",
  "awaiting_validation",
]);
const HISTORY_STATUSES = new Set([
  "completed",
  "validated",
  "declined",
  "refused",
  "cancelled",
  "disputed",
]);

function bookingToMission(b: Booking): MissionData {
  return {
    id: b.booking_id,
    kind: "booking",
    client_name: b.client_name,
    trade_name: b.trade_name,
    date: b.date,
    slot: b.slot,
    description: b.description,
    status: b.status,
    urgent: b.urgent,
  };
}

function interventionToMission(iv: Intervention): MissionData {
  return {
    id: iv.intervention_id,
    kind: "intervention",
    client_name: iv.client_name || "Client",
    trade_name: iv.trade,
    description: iv.description,
    status: iv.status,
    urgent: iv.urgency === "urgence",
    amount_cents: iv.total_amount_cents || iv.balance_cents,
  };
}

export default function ArtisanMissions() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [availableNow, setAvailableNow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [segment, setSegment] = useState<Segment>("todo");
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const posRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { alert: urgentAlert, dismiss: dismissAlert } = useUrgentAlert({
    intervalMs: 8000,
  });

  const load = useCallback(async () => {
    try {
      const [profile, bk, ivs] = await Promise.all([
        api<{ available_now?: boolean } | null>("/artisans/me").catch(() => null),
        api<Booking[]>("/bookings/received").catch(() => []),
        api<Intervention[]>("/interventions/mine").catch(() => []),
      ]);
      setAvailableNow(!!profile?.available_now);
      setBookings(bk || []);
      setInterventions(ivs || []);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  // Push position every 20s while "available_now" (moved from legacy live).
  useEffect(() => {
    const start = async () => {
      try {
        const perm = await Location.requestForegroundPermissionsAsync();
        if (perm.status !== "granted") return;
        const push = async () => {
          try {
            const pos = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });
            await api("/artisans/me/position", {
              method: "POST",
              body: {
                lat: pos.coords.latitude,
                lng: pos.coords.longitude,
                available_now: availableNow,
              },
            });
          } catch {
            /* silent */
          }
        };
        push();
        if (posRef.current) clearInterval(posRef.current);
        posRef.current = setInterval(push, 20000);
      } catch {
        /* permissions denied or web fallback */
      }
    };
    if (availableNow) {
      start();
    } else if (posRef.current) {
      clearInterval(posRef.current);
      posRef.current = null;
    }
    return () => {
      if (posRef.current) clearInterval(posRef.current);
    };
  }, [availableNow]);

  const toggleAvailable = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setBusy(true);
    try {
      const res = await api<{ available_now: boolean }>(
        "/artisans/me/available-now",
        { method: "POST" },
      );
      setAvailableNow(res.available_now);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur inconnue";
      Alert.alert("Erreur", msg);
    } finally {
      setBusy(false);
    }
  };

  const setBookingStatus = async (id: string, status: string) => {
    try {
      await api(`/bookings/${id}`, { method: "PATCH", body: { status } });
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", msg);
    }
  };

  const ivRespond = async (id: string, action: "accept" | "refuse") => {
    try {
      await api(`/interventions/${id}/${action}`, {
        method: "POST",
        body: action === "refuse" ? { reason: "Non disponible" } : {},
      });
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", msg);
    }
  };

  const ivStart = async (id: string) => {
    try {
      await api(`/interventions/${id}/start`, { method: "POST" });
      load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", msg);
    }
  };

  const ivFinish = async (id: string) => {
    // Simple confirmation prompt — sur mobile natif Alert.prompt existe.
    // Web fallback : montant par défaut 250€.
    if (typeof Alert.prompt === "function") {
      Alert.prompt(
        "Montant total (€)",
        "Entrez le montant total à facturer :",
        async (val) => {
          const total = parseFloat(String(val || "0"));
          if (!total || total <= 0) return;
          try {
            await api(`/interventions/${id}/finish`, {
              method: "POST",
              body: { total_amount_cents: Math.round(total * 100) },
            });
            load();
          } catch (e) {
            const msg = e instanceof Error ? e.message : "Erreur";
            Alert.alert("Erreur", msg);
          }
        },
      );
    } else {
      try {
        await api(`/interventions/${id}/finish`, {
          method: "POST",
          body: { total_amount_cents: 25000 },
        });
        load();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Erreur";
        Alert.alert("Erreur", msg);
      }
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  // Partition
  const partitions = useMemo(() => {
    const todo: {
      bookings: Booking[];
      interventions: Intervention[];
    } = { bookings: [], interventions: [] };
    const active: {
      bookings: Booking[];
      interventions: Intervention[];
    } = { bookings: [], interventions: [] };
    const history: {
      bookings: Booking[];
      interventions: Intervention[];
    } = { bookings: [], interventions: [] };
    for (const b of bookings) {
      if (TODO_STATUSES.has(b.status)) todo.bookings.push(b);
      else if (ACTIVE_STATUSES.has(b.status)) active.bookings.push(b);
      else if (HISTORY_STATUSES.has(b.status)) history.bookings.push(b);
    }
    for (const iv of interventions) {
      if (TODO_STATUSES.has(iv.status)) todo.interventions.push(iv);
      else if (ACTIVE_STATUSES.has(iv.status)) active.interventions.push(iv);
      else if (HISTORY_STATUSES.has(iv.status)) history.interventions.push(iv);
    }
    return { todo, active, history };
  }, [bookings, interventions]);

  const todoCount =
    partitions.todo.bookings.length + partitions.todo.interventions.length;
  const activeCount =
    partitions.active.bookings.length + partitions.active.interventions.length;
  const historyCount = Math.min(
    30,
    partitions.history.bookings.length + partitions.history.interventions.length,
  );
  const badge = (n: number) => (n > 0 ? n.toString() : "");

  // Urgent (top of "todo")
  const urgent = useMemo(
    () => [
      ...partitions.todo.bookings.filter((b) => b.urgent),
      ...partitions.todo.interventions.filter((iv) => iv.urgency === "urgence"),
    ],
    [partitions],
  );

  const openMission = (m: MissionData) => {
    if (m.kind === "intervention") {
      router.push({ pathname: "/intervention/[id]", params: { id: m.id } });
    } else {
      router.push({ pathname: "/track/[id]", params: { id: m.id } });
    }
  };

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
        {/* --- Header ------------------------------------------------- */}
        <View style={styles.header}>
          <Txt size="sm" color={colors.muted}>
            Missions
          </Txt>
          <Txt weight="extrabold" size="3xl" style={{ marginTop: 2 }}>
            Mes missions
          </Txt>
        </View>

        {/* --- Available now ---------------------------------------- */}
        <View style={styles.availCard}>
          <View style={{ flex: 1 }}>
            <View style={styles.availTitle}>
              <View
                style={[
                  styles.availDot,
                  { backgroundColor: availableNow ? colors.success : colors.muted },
                ]}
              />
              <Txt weight="bold" size="lg">
                {availableNow ? "Disponible maintenant" : "Non disponible"}
              </Txt>
            </View>
            <Txt
              size="sm"
              color={colors.muted}
              style={{ marginTop: 6, lineHeight: 20 }}
            >
              {availableNow
                ? "Votre position est partagée avec les clients à proximité."
                : "Activez pour recevoir des demandes d'intervention immédiate."}
            </Txt>
          </View>
          <Switch
            testID="toggle-available"
            value={availableNow}
            onValueChange={toggleAvailable}
            disabled={busy}
            trackColor={{ true: colors.brand, false: colors.borderStrong }}
            thumbColor={colors.surface}
          />
        </View>

        {/* --- Segment control -------------------------------------- */}
        <View style={styles.segment}>
          {SEGMENTS.map((s) => {
            const active = segment === s.key;
            const count =
              s.key === "todo"
                ? todoCount
                : s.key === "active"
                  ? activeCount
                  : historyCount;
            return (
              <Pressable
                key={s.key}
                testID={`seg-${s.key}`}
                onPress={() => setSegment(s.key)}
                style={[styles.segItem, active && styles.segItemActive]}
              >
                <Txt
                  weight="bold"
                  size="sm"
                  color={active ? colors.textInverse : colors.muted}
                >
                  {s.label}
                </Txt>
                {badge(count) ? (
                  <View
                    style={[
                      styles.segBadge,
                      active
                        ? { backgroundColor: colors.textInverse }
                        : { backgroundColor: colors.borderStrong },
                    ]}
                  >
                    <Txt
                      weight="bold"
                      size="sm"
                      color={active ? colors.brand : colors.onSurface}
                    >
                      {badge(count)}
                    </Txt>
                  </View>
                ) : null}
              </Pressable>
            );
          })}
        </View>

        {/* --- List ------------------------------------------------- */}
        {loading ? (
          <View style={{ paddingTop: 40 }}>
            <ActivityIndicator color={colors.brand} />
          </View>
        ) : (
          <View style={styles.listWrap}>
            {segment === "todo" && (
              <>
                {urgent.length > 0 && (
                  <View style={styles.urgentBlock}>
                    <View style={styles.urgentTag}>
                      <View style={styles.urgentDot} />
                      <Txt
                        weight="extrabold"
                        size="sm"
                        color={colors.textInverse}
                        style={{ letterSpacing: 1.5 }}
                      >
                        URGENT
                      </Txt>
                    </View>
                    <Txt
                      weight="bold"
                      size="lg"
                      style={{ marginLeft: spacing.sm }}
                    >
                      {urgent.length} demande{urgent.length > 1 ? "s" : ""} prioritaire
                      {urgent.length > 1 ? "s" : ""}
                    </Txt>
                  </View>
                )}
                {todoCount === 0 ? (
                  <EmptyBlock
                    icon="mail-open-outline"
                    text="Aucune demande à traiter. Restez disponible pour en recevoir."
                  />
                ) : (
                  <>
                    {partitions.todo.bookings.map((b) => (
                      <RequestCard
                        key={b.booking_id}
                        request={b}
                        onAccept={(id) => setBookingStatus(id, "accepted")}
                        onDecline={(id) => setBookingStatus(id, "declined")}
                        onOpen={(id) =>
                          router.push({
                            pathname: "/track/[id]",
                            params: { id },
                          })
                        }
                      />
                    ))}
                    {partitions.todo.interventions.map((iv) => (
                      <MissionCard
                        key={iv.intervention_id}
                        mission={interventionToMission(iv)}
                        onOpen={openMission}
                        actions={[
                          {
                            label: "Refuser",
                            onPress: () => ivRespond(iv.intervention_id, "refuse"),
                            variant: "ghost",
                            testID: `iv-refuse-${iv.intervention_id}`,
                          },
                          {
                            label: "Accepter",
                            icon: "checkmark",
                            onPress: () => ivRespond(iv.intervention_id, "accept"),
                            variant: "primary",
                            testID: `iv-accept-${iv.intervention_id}`,
                          },
                        ]}
                      />
                    ))}
                  </>
                )}
              </>
            )}

            {segment === "active" && (
              <>
                {activeCount === 0 ? (
                  <EmptyBlock
                    icon="briefcase-outline"
                    text="Aucune mission en cours pour le moment."
                  />
                ) : (
                  <>
                    {partitions.active.bookings.map((b) => (
                      <MissionCard
                        key={b.booking_id}
                        mission={bookingToMission(b)}
                        onOpen={openMission}
                        actions={[
                          {
                            label: "Message",
                            icon: "chatbubble-ellipses-outline",
                            onPress: () =>
                              b.conversation_id &&
                              router.push({
                                pathname: "/chat/[id]",
                                params: {
                                  id: b.conversation_id,
                                  name: b.client_name,
                                },
                              }),
                            variant: "ghost",
                            testID: `bk-msg-${b.booking_id}`,
                          },
                          {
                            label: "Terminer",
                            icon: "checkmark-done",
                            onPress: () =>
                              setBookingStatus(b.booking_id, "completed"),
                            variant: "primary",
                            testID: `bk-finish-${b.booking_id}`,
                          },
                        ]}
                      />
                    ))}
                    {partitions.active.interventions.map((iv) => {
                      const actions: Action[] = [];
                      if (iv.status === "confirmed" || iv.status === "accepted") {
                        actions.push({
                          label: "Démarrer",
                          icon: "play",
                          onPress: () => ivStart(iv.intervention_id),
                          variant: "primary",
                          testID: `iv-start-${iv.intervention_id}`,
                        });
                      } else if (iv.status === "in_progress") {
                        actions.push({
                          label: "Terminer",
                          icon: "checkmark-done",
                          onPress: () => ivFinish(iv.intervention_id),
                          variant: "primary",
                          testID: `iv-finish-${iv.intervention_id}`,
                        });
                      }
                      return (
                        <MissionCard
                          key={iv.intervention_id}
                          mission={interventionToMission(iv)}
                          onOpen={openMission}
                          actions={actions}
                        />
                      );
                    })}
                  </>
                )}
              </>
            )}

            {segment === "history" && (
              <>
                {historyCount === 0 ? (
                  <EmptyBlock
                    icon="archive-outline"
                    text="Votre historique est vide."
                  />
                ) : (
                  <>
                    {partitions.history.bookings.slice(0, 30).map((b) => (
                      <MissionCard
                        key={b.booking_id}
                        mission={bookingToMission(b)}
                        onOpen={openMission}
                      />
                    ))}
                    {partitions.history.interventions.slice(0, 30).map((iv) => (
                      <MissionCard
                        key={iv.intervention_id}
                        mission={interventionToMission(iv)}
                        onOpen={openMission}
                      />
                    ))}
                  </>
                )}
              </>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

function EmptyBlock({
  icon,
  text,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
}) {
  return (
    <View style={styles.emptyCard}>
      <Ionicons name={icon} size={26} color={colors.muted} />
      <Txt
        size="sm"
        color={colors.muted}
        style={{ marginTop: spacing.md, textAlign: "center", lineHeight: 20 }}
      >
        {text}
      </Txt>
    </View>
  );
}

// Duplicate Action type import to keep MissionCard's Action structural type
// aligned with what we pass (icon typing must resolve to Ionicons glyphs).
type Action = {
  label: string;
  onPress: () => void;
  variant?: "primary" | "ghost";
  icon?: keyof typeof Ionicons.glyphMap;
  testID?: string;
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  header: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.lg,
  },
  availCard: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: spacing.lg,
    padding: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    marginBottom: spacing.lg,
  },
  availTitle: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  availDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  segment: {
    flexDirection: "row",
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: 4,
    marginBottom: spacing.lg,
  },
  segItem: {
    flex: 1,
    height: 38,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
  },
  segItemActive: {
    backgroundColor: colors.brand,
  },
  segBadge: {
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    paddingHorizontal: 6,
    alignItems: "center",
    justifyContent: "center",
  },
  listWrap: {
    paddingHorizontal: spacing.lg,
  },
  urgentBlock: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
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
  urgentDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.textInverse,
  },
  emptyCard: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
});
