/**
 * Live Map screen — Uber-style intervention immédiate.
 * Client sees verified pros around them in real-time.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, StyleSheet, Pressable, ScrollView, Alert, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInUp, FadeIn } from "react-native-reanimated";
import { Image } from "expo-image";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import LiveMap from "@/src/components/LiveMap";

const COLORS = {
  bg: "#0B0B0B",
  bgSoft: "#141416",
  white: "#FFFFFF",
  accent: "#C8A96B",
  secondary: "#B8B8B8",
  muted: "#6E6E73",
  border: "#1F1F22",
  success: "#34D399",
};

const RADIUS_STEPS = [2, 5, 10, 25, 50] as const;
const PARIS_DEFAULT = { lat: 48.8566, lng: 2.3522 };

type Artisan = {
  artisan_id: string;
  name: string;
  photo?: string;
  trade_name: string;
  rating: number;
  hourly_rate: number;
  current_lat: number;
  current_lng: number;
  distance_km: number;
  eta_min: number;
  available_now?: boolean;
  identity_verified?: boolean;
  insurance_verified?: boolean;
};

export default function LiveMapScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{
    trade?: string;
    trade_label?: string;
    description?: string;
    urgency?: string;
  }>();

  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);
  const [radius, setRadius] = useState<number>(5);
  const [onlyAvailable, setOnlyAvailable] = useState<boolean>(false);
  const [artisans, setArtisans] = useState<Artisan[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Artisan | null>(null);
  const [requesting, setRequesting] = useState(false);
  const pollRef = useRef<any>(null);

  // Get location
  useEffect(() => {
    (async () => {
      try {
        const perm = await Location.requestForegroundPermissionsAsync();
        if (perm.status === "granted") {
          const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          setCenter({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        } else {
          setCenter(PARIS_DEFAULT);
        }
      } catch {
        setCenter(PARIS_DEFAULT);
      }
    })();
  }, []);

  const load = useCallback(async () => {
    if (!center) return;
    try {
      const q = new URLSearchParams({
        lat: String(center.lat),
        lng: String(center.lng),
        radius: String(radius),
        only_available_now: String(onlyAvailable),
      });
      if (params.trade) q.set("category", String(params.trade));
      const res = await api<{ artisans: Artisan[] }>(`/artisans/nearby?${q.toString()}`, { auth: false });
      setArtisans(res.artisans);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [center, radius, onlyAvailable, params.trade]);

  // Initial + polling every 8s (live positions)
  useEffect(() => {
    if (!center) return;
    load();
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(load, 8000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [center, radius, onlyAvailable, load]);

  const requestNow = async () => {
    if (!selected || !center) return;
    setRequesting(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {});
    try {
      const iv = await api<{ intervention_id: string }>("/interventions/request", {
        method: "POST",
        body: {
          artisan_id: selected.artisan_id,
          description: params.description || "Demande urgente",
          lat: center.lat,
          lng: center.lng,
          trade: params.trade,
          urgency: params.urgency,
        },
      });
      Alert.alert(
        "Demande envoyée",
        `${selected.name} a été notifié. Vous recevrez sa réponse d'ici quelques minutes.`,
        [{ text: "OK", onPress: () => router.replace({ pathname: "/intervention/[id]", params: { id: iv.intervention_id } }) }]
      );
    } catch (e: any) {
      Alert.alert("Erreur", e?.message || "Impossible d'envoyer la demande.");
    } finally {
      setRequesting(false);
    }
  };

  const availableCount = useMemo(() => artisans.filter((a) => a.available_now).length, [artisans]);

  return (
    <View style={styles.container}>
      {/* Map */}
      <View style={styles.mapWrap}>
        {center ? (
          <LiveMap
            center={center}
            radius={radius}
            artisans={artisans}
            onSelect={(a) => {
              setSelected(a);
              Haptics.selectionAsync().catch(() => {});
            }}
            selectedId={selected?.artisan_id}
          />
        ) : (
          <View style={styles.mapLoader}>
            <ActivityIndicator color={COLORS.accent} size="large" />
          </View>
        )}
      </View>

      {/* Header */}
      <View style={[styles.header, { top: insets.top + 12 }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn} hitSlop={12}>
          <Ionicons name="chevron-back" size={22} color={COLORS.white} />
        </Pressable>
        <View style={styles.headerCenter}>
          <Txt weight="extrabold" size="base" style={{ color: COLORS.white }}>
            {params.trade_label || "Intervention immédiate"}
          </Txt>
          <Txt size="sm" style={{ color: COLORS.secondary }}>
            {loading ? "Recherche en cours…" : `${artisans.length} pro${artisans.length > 1 ? "s" : ""} · ${availableCount} dispo`}
          </Txt>
        </View>
        <View style={{ width: 40 }} />
      </View>

      {/* Radius selector */}
      <Animated.View entering={FadeIn.duration(400)} style={[styles.radiusRow, { top: insets.top + 80 }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 8 }}>
          {RADIUS_STEPS.map((r) => (
            <Pressable
              key={r}
              testID={`radius-${r}`}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                setRadius(r);
              }}
              style={[styles.chip, radius === r && styles.chipActive]}
            >
              <Txt size="sm" weight="bold" style={{ color: radius === r ? COLORS.bg : COLORS.white }}>
                {r} km
              </Txt>
            </Pressable>
          ))}
          <Pressable
            testID="only-available"
            onPress={() => {
              Haptics.selectionAsync().catch(() => {});
              setOnlyAvailable((v) => !v);
            }}
            style={[styles.chipOutline, onlyAvailable && styles.chipActive]}
          >
            <View style={styles.liveDot} />
            <Txt size="sm" weight="bold" style={{ color: onlyAvailable ? COLORS.bg : COLORS.white, marginLeft: 4 }}>
              Dispo maintenant
            </Txt>
          </Pressable>
        </ScrollView>
      </Animated.View>

      {/* Bottom sheet (selected pro or artisan list) */}
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
        {selected ? (
          <SelectedPro
            artisan={selected}
            onClose={() => setSelected(null)}
            onRequest={requestNow}
            requesting={requesting}
            onBookSlot={() => router.push({ pathname: "/artisan/[id]", params: { id: selected.artisan_id } })}
          />
        ) : (
          <View>
            <View style={styles.handleBar} />
            {artisans.length === 0 && !loading && (
              <View style={{ alignItems: "center", paddingVertical: 20 }}>
                <Ionicons name="search-outline" size={26} color={COLORS.muted} />
                <Txt style={{ marginTop: 8, color: COLORS.secondary, textAlign: "center" }}>
                  Aucun pro trouvé dans un rayon de {radius} km.
                </Txt>
                <Txt size="sm" style={{ marginTop: 4, color: COLORS.muted }}>Élargissez la recherche</Txt>
              </View>
            )}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 16, gap: 10 }}>
              {artisans.slice(0, 12).map((a, i) => (
                <Animated.View key={a.artisan_id} entering={FadeInUp.delay(i * 60).duration(400)}>
                  <Pressable
                    onPress={() => {
                      Haptics.selectionAsync().catch(() => {});
                      setSelected(a);
                    }}
                    style={styles.miniCard}
                  >
                    <View style={styles.miniAvatar}>
                      {a.photo ? (
                        <Image source={{ uri: a.photo }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
                      ) : (
                        <Ionicons name="person" size={22} color={COLORS.muted} />
                      )}
                      {a.available_now && <View style={styles.miniDotLive} />}
                    </View>
                    <Txt weight="bold" size="sm" style={{ color: COLORS.white, marginTop: 6 }} numberOfLines={1}>
                      {a.name.split(" ")[0]}
                    </Txt>
                    <View style={{ flexDirection: "row", alignItems: "center", marginTop: 2, gap: 4 }}>
                      <Ionicons name="star" size={10} color={COLORS.accent} />
                      <Txt size="sm" style={{ color: COLORS.secondary, fontSize: 11 }}>
                        {a.rating.toFixed(1)}
                      </Txt>
                    </View>
                    <Txt size="sm" style={{ color: COLORS.muted, marginTop: 2, fontSize: 11 }}>
                      {a.eta_min} min · {a.distance_km} km
                    </Txt>
                  </Pressable>
                </Animated.View>
              ))}
            </ScrollView>
          </View>
        )}
      </View>
    </View>
  );
}

function SelectedPro({
  artisan: a,
  onClose,
  onRequest,
  onBookSlot,
  requesting,
}: {
  artisan: Artisan;
  onClose: () => void;
  onRequest: () => void;
  onBookSlot: () => void;
  requesting: boolean;
}) {
  return (
    <Animated.View entering={FadeInUp.duration(300)}>
      <View style={styles.handleBar} />
      <View style={styles.selectedHeader}>
        <View style={styles.selectedAvatar}>
          {a.photo ? (
            <Image source={{ uri: a.photo }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
          ) : (
            <Ionicons name="person" size={30} color={COLORS.muted} />
          )}
          {a.available_now && <View style={styles.selectedDotLive} />}
        </View>
        <View style={{ flex: 1, marginLeft: 14 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Txt weight="extrabold" size="lg" style={{ color: COLORS.white }} numberOfLines={1}>
              {a.name}
            </Txt>
            {a.identity_verified && (
              <View style={styles.verifBadge}>
                <Ionicons name="checkmark" size={9} color={COLORS.bg} />
              </View>
            )}
          </View>
          <Txt size="sm" style={{ color: COLORS.secondary, marginTop: 2 }}>
            {a.trade_name}
          </Txt>
          <View style={{ flexDirection: "row", gap: 12, marginTop: 6 }}>
            <View style={styles.metaChip}>
              <Ionicons name="star" size={11} color={COLORS.accent} />
              <Txt size="sm" style={{ color: COLORS.white, marginLeft: 4 }}>{a.rating.toFixed(1)}</Txt>
            </View>
            <View style={styles.metaChip}>
              <Ionicons name="time-outline" size={11} color={COLORS.secondary} />
              <Txt size="sm" style={{ color: COLORS.white, marginLeft: 4 }}>{a.eta_min} min</Txt>
            </View>
            <View style={styles.metaChip}>
              <Ionicons name="location-outline" size={11} color={COLORS.secondary} />
              <Txt size="sm" style={{ color: COLORS.white, marginLeft: 4 }}>{a.distance_km} km</Txt>
            </View>
            <View style={styles.metaChip}>
              <Ionicons name="cash-outline" size={11} color={COLORS.secondary} />
              <Txt size="sm" style={{ color: COLORS.white, marginLeft: 4 }}>{a.hourly_rate}€/h</Txt>
            </View>
          </View>
        </View>
        <Pressable onPress={onClose} hitSlop={12} style={styles.closeBtn}>
          <Ionicons name="close" size={18} color={COLORS.white} />
        </Pressable>
      </View>

      <View style={{ paddingHorizontal: 16, marginTop: 14, gap: 10 }}>
        <Pressable
          testID="request-now-btn"
          onPress={onRequest}
          disabled={requesting}
          style={({ pressed }) => [styles.primaryBtn, (pressed || requesting) && { opacity: 0.85 }]}
        >
          {requesting ? (
            <ActivityIndicator color={COLORS.bg} />
          ) : (
            <>
              <Ionicons name="flash" size={18} color={COLORS.bg} />
              <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 8 }}>
                Demander maintenant
              </Txt>
            </>
          )}
        </Pressable>

        <Pressable onPress={onBookSlot} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.7 }]}>
          <Ionicons name="calendar-outline" size={18} color={COLORS.white} />
          <Txt weight="semibold" style={{ color: COLORS.white, marginLeft: 8 }}>
            Voir la fiche & créneaux
          </Txt>
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  mapWrap: { flex: 1 },
  mapLoader: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.bg,
  },
  header: {
    position: "absolute",
    left: 12,
    right: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "rgba(11,11,11,0.75)",
    borderRadius: 16,
    padding: 8,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  headerCenter: { flex: 1, alignItems: "center" },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(255,255,255,0.05)",
    alignItems: "center", justifyContent: "center",
  },
  radiusRow: {
    position: "absolute",
    left: 0,
    right: 0,
  },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8,
    backgroundColor: "rgba(11,11,11,0.75)",
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.border,
  },
  chipOutline: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: "rgba(11,11,11,0.75)",
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.success,
  },
  chipActive: {
    backgroundColor: COLORS.accent,
    borderColor: COLORS.accent,
  },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.success },

  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: COLORS.bg,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 8,
    borderTopWidth: 1,
    borderColor: COLORS.border,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: -8 },
    shadowOpacity: 0.5,
    shadowRadius: 24,
    elevation: 12,
  },
  handleBar: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: COLORS.border,
    alignSelf: "center",
    marginBottom: 12,
  },
  miniCard: {
    width: 92,
    padding: 8,
    borderRadius: 14,
    backgroundColor: COLORS.bgSoft,
    borderWidth: 1, borderColor: COLORS.border,
    alignItems: "center",
  },
  miniAvatar: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: COLORS.bg,
    overflow: "hidden",
    alignItems: "center", justifyContent: "center",
  },
  miniDotLive: {
    position: "absolute", bottom: 0, right: 0,
    width: 12, height: 12, borderRadius: 6,
    backgroundColor: COLORS.success,
    borderWidth: 2, borderColor: COLORS.bgSoft,
  },
  selectedHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
  },
  selectedAvatar: {
    width: 60, height: 60, borderRadius: 30,
    backgroundColor: COLORS.bgSoft,
    overflow: "hidden",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  selectedDotLive: {
    position: "absolute", bottom: 0, right: 0,
    width: 14, height: 14, borderRadius: 7,
    backgroundColor: COLORS.success,
    borderWidth: 2, borderColor: COLORS.bgSoft,
  },
  verifBadge: {
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: COLORS.accent,
    alignItems: "center", justifyContent: "center",
  },
  metaChip: { flexDirection: "row", alignItems: "center" },
  closeBtn: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: COLORS.bgSoft,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: COLORS.border,
  },
  primaryBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: 16,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    shadowColor: COLORS.accent,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 16,
    elevation: 6,
  },
  secondaryBtn: {
    borderRadius: 16,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.bgSoft,
  },
});
