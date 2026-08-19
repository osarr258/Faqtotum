/**
 * Track — FAQTOTUM V1 (suivi client d'un booking).
 *
 * Cet écran remplace l'ancien tracking mission. Il consomme le nouvel
 * endpoint unifié `GET /api/tracking/{booking_id}` et se met à jour
 * toutes les 4 s tant que l'intervention est en cours.
 *
 * Statuts FAQTOTUM (brief §16) :
 *   pending → accepted (Artisan trouvé) → en_route → arrived
 *          → in_progress → completed
 *
 * La carte affiche : position artisan (si envoyée), destination client,
 * ligne pointillée entre les deux. Sur web = fallback stylisé.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  StyleSheet,
  Pressable,
  ActivityIndicator,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar, Button } from "@/src/components/ui";
import TrackMap from "@/src/components/TrackMap";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Tracking = {
  booking_id: string;
  status: string;
  urgent?: boolean;
  date?: string;
  slot?: string;
  description?: string;
  estimated_price_min_eur?: number | null;
  estimated_price_max_eur?: number | null;
  artisan?: {
    artisan_id?: string;
    name?: string;
    title?: string;
    photo?: string | null;
    trade_name?: string;
    rating?: number;
    current_lat?: number | null;
    current_lng?: number | null;
    response_min?: number;
  } | null;
};

const STEPS: { key: string; label: string; icon: any }[] = [
  { key: "pending", label: "Demande", icon: "sparkles" },
  { key: "accepted", label: "Artisan trouvé", icon: "person-circle" },
  { key: "en_route", label: "En route", icon: "car-sport" },
  { key: "arrived", label: "Arrivé", icon: "location" },
  { key: "in_progress", label: "En cours", icon: "construct" },
  { key: "completed", label: "Terminée", icon: "flag" },
];

const STATUS_LABEL: Record<string, string> = {
  pending: "Recherche d'un artisan",
  accepted: "Artisan confirmé",
  confirmed: "Artisan confirmé",
  professional_on_the_way: "En route vers vous",
  en_route: "En route vers vous",
  arrived: "Artisan sur place",
  in_progress: "Intervention en cours",
  awaiting_validation: "À valider",
  completed: "Intervention terminée",
  cancelled: "Annulée",
  declined: "Refusée",
};

function statusIndex(status: string): number {
  const map: Record<string, number> = {
    pending: 0,
    accepted: 1,
    confirmed: 1,
    professional_on_the_way: 2,
    en_route: 2,
    arrived: 3,
    in_progress: 4,
    awaiting_validation: 4,
    completed: 5,
  };
  return map[status] ?? 0;
}

export default function TrackScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [t, setT] = useState<Tracking | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api<Tracking>(`/tracking/${id}`);
      setT(data);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, 4000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  if (loading || !t) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.brand} size="large" />
      </View>
    );
  }

  const idx = statusIndex(t.status);
  const label = STATUS_LABEL[t.status] || t.status;
  const artisanName = t.artisan?.name || "Artisan";
  const artisanTrade = t.artisan?.trade_name || t.artisan?.title || "";
  const artisanLat = t.artisan?.current_lat ?? null;
  const artisanLng = t.artisan?.current_lng ?? null;
  // Client point is not exposed by public tracking (privacy). We use the
  // artisan position as center on the map when available.
  const artisanPt = artisanLat != null && artisanLng != null
    ? { lat: artisanLat, lng: artisanLng }
    : { lat: 48.858, lng: 2.349 };
  const clientPt = { lat: 48.858, lng: 2.349 };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={styles.mapWrap}>
        <TrackMap artisan={artisanPt} client={clientPt} status={t.status} />
        <Pressable
          testID="close-btn"
          onPress={() => router.replace("/(client)")}
          style={[styles.iconBtn, { top: insets.top + spacing.sm }]}
        >
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
        {t.urgent ? (
          <View style={[styles.urgentBadge, { top: insets.top + spacing.sm }]}>
            <Ionicons name="flash" size={12} color={colors.textInverse} />
            <Txt
              weight="extrabold"
              size="sm"
              color={colors.textInverse}
              style={{ marginLeft: 4, letterSpacing: 1 }}
            >
              URGENT
            </Txt>
          </View>
        ) : null}
      </View>

      <View
        style={[
          styles.sheet,
          { paddingBottom: insets.bottom + spacing.lg },
        ]}
      >
        {/* Steps */}
        <View style={styles.stepper}>
          {STEPS.map((s, i) => {
            const done = i < idx;
            const current = i === idx;
            const active = done || current;
            return (
              <View key={s.key} style={styles.step}>
                {i > 0 && (
                  <View
                    style={[
                      styles.stepLine,
                      {
                        backgroundColor:
                          i <= idx ? colors.brand : colors.surfaceSecondary,
                      },
                    ]}
                  />
                )}
                <View
                  style={[
                    styles.stepDot,
                    {
                      backgroundColor: active
                        ? colors.brand
                        : colors.surfaceSecondary,
                      borderColor: current ? colors.brand : "transparent",
                    },
                  ]}
                >
                  <Ionicons
                    name={done ? "checkmark" : s.icon}
                    size={13}
                    color={active ? colors.textInverse : colors.muted}
                  />
                </View>
                <Txt
                  size="sm"
                  color={active ? colors.onSurface : colors.muted}
                  style={{ marginTop: 4, fontSize: 10 }}
                  numberOfLines={1}
                >
                  {s.label}
                </Txt>
              </View>
            );
          })}
        </View>

        {/* Status */}
        <View style={styles.statusRow}>
          <View style={styles.statusIcon}>
            <Ionicons
              name={STEPS[idx]?.icon || "sparkles"}
              size={22}
              color={colors.textInverse}
            />
          </View>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="extrabold" size="lg">
              {label}
            </Txt>
            {t.status === "en_route" || t.status === "professional_on_the_way" ? (
              <Txt color={colors.muted} size="sm">
                Votre artisan est en chemin.
              </Txt>
            ) : t.status === "arrived" ? (
              <Txt color={colors.muted} size="sm">
                Ouvrez la porte à votre artisan.
              </Txt>
            ) : t.status === "in_progress" ? (
              <Txt color={colors.muted} size="sm">
                L&apos;intervention est en cours.
              </Txt>
            ) : t.status === "completed" ? (
              <Txt color={colors.muted} size="sm">
                Merci d&apos;avoir choisi Faqtotum.
              </Txt>
            ) : (
              <Txt color={colors.muted} size="sm">
                Nous vous tenons informé en temps réel.
              </Txt>
            )}
          </View>
        </View>

        {/* Artisan card */}
        {t.artisan?.name && (
          <View style={styles.proRow}>
            <Avatar name={artisanName} uri={t.artisan.photo || null} size={52} />
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold" size="base">
                {artisanName}
              </Txt>
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                {t.artisan.rating ? (
                  <>
                    <Ionicons name="star" size={13} color={colors.brand} />
                    <Txt
                      size="sm"
                      color={colors.muted}
                      style={{ marginLeft: 4 }}
                    >
                      {t.artisan.rating.toFixed(1)}
                    </Txt>
                    <Txt size="sm" color={colors.muted}>
                      {artisanTrade ? ` · ${artisanTrade}` : ""}
                    </Txt>
                  </>
                ) : (
                  <Txt size="sm" color={colors.muted}>
                    {artisanTrade}
                  </Txt>
                )}
              </View>
            </View>
            <Pressable
              testID="chat-button"
              onPress={() =>
                router.push({
                  pathname: "/chat/[id]",
                  params: { id: t.booking_id, name: artisanName },
                })
              }
              style={styles.chatBtn}
            >
              <Ionicons
                name="chatbubble-outline"
                size={20}
                color={colors.textInverse}
              />
            </Pressable>
          </View>
        )}

        {/* Completed → review CTA */}
        {t.status === "completed" && (
          <Button
            testID="rate-btn"
            title="Noter mon artisan"
            onPress={() =>
              router.push({
                pathname: "/review",
                params: { booking_id: t.booking_id },
              })
            }
            style={{ marginTop: spacing.lg }}
          />
        )}
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
  mapWrap: {
    flex: 1,
    backgroundColor: colors.surfaceSecondary,
  },
  iconBtn: {
    position: "absolute",
    left: spacing.lg,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  urgentBadge: {
    position: "absolute",
    right: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.sm,
    backgroundColor: colors.error,
  },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    borderTopWidth: 1,
    borderColor: colors.border,
  },
  stepper: {
    flexDirection: "row",
    marginBottom: spacing.lg,
  },
  step: {
    flex: 1,
    alignItems: "center",
  },
  stepLine: {
    position: "absolute",
    top: 13,
    right: "50%",
    width: "100%",
    height: 2,
  },
  stepDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  statusIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
  proRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.lg,
    paddingTop: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  chatBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
  },
});
