/**
 * Artisan Live Hub — "Available now" toggle, live position, intervention inbox, manual slots.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Switch, Alert, ActivityIndicator, TextInput } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { FadeInUp } from "react-native-reanimated";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";

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
  description: string;
  status: string;
  created_at: string;
  client_name?: string;
  trade?: string;
  urgency?: string;
  price_estimate_min?: number;
  price_estimate_max?: number;
};

type Slot = { slot_id: string; date: string; start_time: string; duration_min: number };

export default function ArtisanLive() {
  const insets = useSafeAreaInsets();
  const [availableNow, setAvailableNow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(true);
  const [newDate, setNewDate] = useState("");
  const [newTime, setNewTime] = useState("");
  const [addingSlot, setAddingSlot] = useState(false);
  const posRef = useRef<any>(null);

  const load = useCallback(async () => {
    try {
      const [profile, ivs, mySlots] = await Promise.all([
        api<any>("/artisans/me"),
        api<Intervention[]>("/interventions/mine"),
        api<{ slots: Slot[] }>("/artisans/me/slots"),
      ]);
      setAvailableNow(!!profile.available_now);
      setInterventions(ivs);
      setSlots(mySlots.slots || []);
    } catch {}
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  // Poll interventions every 6s
  useEffect(() => {
    const iv = setInterval(load, 6000);
    return () => clearInterval(iv);
  }, [load]);

  // Push position every 20s while "available_now"
  useEffect(() => {
    const start = async () => {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== "granted") return;
      const push = async () => {
        try {
          const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
          await api("/artisans/me/position", {
            method: "POST",
            body: { lat: pos.coords.latitude, lng: pos.coords.longitude, available_now: availableNow },
          });
        } catch {}
      };
      push();
      if (posRef.current) clearInterval(posRef.current);
      posRef.current = setInterval(push, 20000);
    };
    if (availableNow) start();
    else if (posRef.current) { clearInterval(posRef.current); posRef.current = null; }
    return () => { if (posRef.current) clearInterval(posRef.current); };
  }, [availableNow]);

  const toggleAvailable = async (v: boolean) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setBusy(true);
    try {
      const res = await api<{ available_now: boolean }>("/artisans/me/available-now", { method: "POST" });
      setAvailableNow(res.available_now);
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    } finally { setBusy(false); }
  };

  const respond = async (iv: Intervention, action: "accept" | "refuse") => {
    try {
      await api(`/interventions/${iv.intervention_id}/${action}`, { method: "POST", body: action === "refuse" ? { reason: "Non disponible" } : {} });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      load();
    } catch (e: any) {
      Alert.alert("Erreur", e?.message);
    }
  };

  const addSlot = async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(newDate) || !/^\d{2}:\d{2}$/.test(newTime)) {
      return Alert.alert("Format", "Date : AAAA-MM-JJ  |  Heure : HH:MM");
    }
    setAddingSlot(true);
    try {
      await api("/artisans/me/slots", { method: "POST", body: { date: newDate, start_time: newTime, duration_min: 60 } });
      setNewDate(""); setNewTime("");
      load();
    } catch (e: any) { Alert.alert("Erreur", e?.message); }
    finally { setAddingSlot(false); }
  };

  const removeSlot = async (id: string) => {
    try {
      await api(`/artisans/me/slots/${id}`, { method: "DELETE" });
      load();
    } catch (e: any) { Alert.alert("Erreur", e?.message); }
  };

  const pending = interventions.filter((i) => i.status === "pending");

  if (loading) {
    return <View style={styles.container}><ActivityIndicator color={COLORS.accent} style={{ marginTop: 60 }} /></View>;
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingTop: insets.top + 12, paddingBottom: insets.bottom + 40 }}
    >
      <View style={styles.headerRow}>
        <Txt weight="extrabold" size="2xl" style={{ color: COLORS.white }}>Live</Txt>
        <Txt size="sm" style={{ color: COLORS.muted }}>Gérez vos interventions en direct</Txt>
      </View>

      {/* Available now toggle */}
      <View style={styles.availCard}>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <View style={[styles.pulseDot, availableNow && { backgroundColor: COLORS.success }]} />
            <Txt weight="bold" size="lg" style={{ color: COLORS.white }}>
              {availableNow ? "Disponible maintenant" : "Non disponible"}
            </Txt>
          </View>
          <Txt size="sm" style={{ color: COLORS.secondary, marginTop: 6, lineHeight: 20 }}>
            {availableNow
              ? "Votre position est partagée avec les clients cherchant une intervention immédiate."
              : "Activez pour recevoir des demandes d'intervention immédiate."}
          </Txt>
        </View>
        <Switch
          testID="toggle-available"
          value={availableNow}
          onValueChange={toggleAvailable}
          disabled={busy}
          trackColor={{ true: COLORS.success, false: COLORS.border }}
          thumbColor={COLORS.white}
        />
      </View>

      {/* Pending interventions */}
      {pending.length > 0 && (
        <View style={{ marginTop: 20 }}>
          <Txt weight="bold" style={styles.sectionH}>Demandes en attente ({pending.length})</Txt>
          {pending.map((iv, i) => (
            <Animated.View key={iv.intervention_id} entering={FadeInUp.delay(i * 80).duration(300)} style={styles.ivCard}>
              <View style={styles.ivRow}>
                <View style={styles.ivIcon}>
                  <Ionicons name="flash" size={16} color={COLORS.accent} />
                </View>
                <View style={{ flex: 1 }}>
                  <Txt weight="bold" style={{ color: COLORS.white }}>{iv.client_name || "Client"}</Txt>
                  <Txt size="sm" style={{ color: COLORS.muted, marginTop: 2 }}>
                    {iv.trade} · {iv.urgency || "standard"}
                  </Txt>
                </View>
              </View>
              <Txt size="sm" style={{ color: COLORS.secondary, marginTop: 8, lineHeight: 20 }} numberOfLines={3}>
                {iv.description}
              </Txt>
              {iv.price_estimate_min != null && (
                <Txt size="sm" style={{ color: COLORS.accent, marginTop: 6 }}>
                  Estimation : {iv.price_estimate_min}-{iv.price_estimate_max} €
                </Txt>
              )}
              <View style={styles.ivActions}>
                <Pressable
                  testID={`refuse-${iv.intervention_id}`}
                  onPress={() => respond(iv, "refuse")}
                  style={({ pressed }) => [styles.btnGhost, pressed && { opacity: 0.7 }]}
                >
                  <Txt weight="bold" style={{ color: COLORS.error }}>Refuser</Txt>
                </Pressable>
                <Pressable
                  testID={`accept-${iv.intervention_id}`}
                  onPress={() => respond(iv, "accept")}
                  style={({ pressed }) => [styles.btnAccept, pressed && { opacity: 0.85 }]}
                >
                  <Ionicons name="checkmark" size={16} color={COLORS.bg} />
                  <Txt weight="bold" style={{ color: COLORS.bg, marginLeft: 6 }}>Accepter</Txt>
                </Pressable>
              </View>
            </Animated.View>
          ))}
        </View>
      )}

      {/* Manual slots */}
      <View style={{ marginTop: 24 }}>
        <Txt weight="bold" style={styles.sectionH}>Mes créneaux ({slots.length})</Txt>
        <Txt size="sm" style={{ color: COLORS.muted, paddingHorizontal: 20, marginBottom: 12 }}>
          Créez vos disponibilités. Les clients pourront réserver ces créneaux.
        </Txt>

        <View style={styles.slotInputRow}>
          <TextInput
            value={newDate}
            onChangeText={setNewDate}
            placeholder="AAAA-MM-JJ"
            placeholderTextColor={COLORS.muted}
            style={styles.input}
          />
          <TextInput
            value={newTime}
            onChangeText={setNewTime}
            placeholder="HH:MM"
            placeholderTextColor={COLORS.muted}
            style={[styles.input, { width: 88 }]}
          />
          <Pressable
            testID="add-slot"
            onPress={addSlot}
            disabled={addingSlot}
            style={({ pressed }) => [styles.addBtn, (addingSlot || pressed) && { opacity: 0.8 }]}
          >
            <Ionicons name="add" size={20} color={COLORS.bg} />
          </Pressable>
        </View>

        {slots.length === 0 && (
          <Txt size="sm" style={{ color: COLORS.muted, textAlign: "center", paddingHorizontal: 20, marginTop: 12 }}>
            Aucun créneau — ajoutez-en pour permettre aux clients de réserver.
          </Txt>
        )}
        {slots.map((s) => (
          <View key={s.slot_id} style={styles.slotRow}>
            <Ionicons name="calendar" size={16} color={COLORS.accent} />
            <Txt weight="semibold" style={{ color: COLORS.white, marginLeft: 8, flex: 1 }}>
              {s.date} · {s.start_time} ({s.duration_min} min)
            </Txt>
            <Pressable onPress={() => removeSlot(s.slot_id)} hitSlop={10}>
              <Ionicons name="trash-outline" size={16} color={COLORS.error} />
            </Pressable>
          </View>
        ))}

        {/* Google Calendar OAuth teaser */}
        <View style={styles.oauthTeaser}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="logo-google" size={16} color={COLORS.accent} />
            <Txt weight="bold" size="sm" style={{ color: COLORS.white }}>Google Calendar / Outlook</Txt>
          </View>
          <Txt size="sm" style={{ color: COLORS.muted, marginTop: 6, lineHeight: 18 }}>
            Connexion OAuth réelle disponible dans le prochain sprint. Vos créneaux se synchroniseront automatiquement.
          </Txt>
          <Pressable
            testID="oauth-teaser"
            onPress={() => Alert.alert("Bientôt disponible", "Connexion Google/Outlook prévue dans le prochain sprint.")}
            style={styles.oauthBtn}
          >
            <Txt size="sm" weight="bold" style={{ color: COLORS.accent }}>M&apos;avertir quand ce sera prêt</Txt>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  headerRow: { paddingHorizontal: 20, marginBottom: 16, gap: 4 },
  availCard: {
    marginHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    padding: 18,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 20,
    borderWidth: 1, borderColor: COLORS.border,
  },
  pulseDot: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: COLORS.muted,
  },
  sectionH: { paddingHorizontal: 20, marginBottom: 10, color: COLORS.white, fontSize: 16 },
  ivCard: {
    marginHorizontal: 20,
    marginBottom: 10,
    padding: 14,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 16,
    borderWidth: 1, borderColor: COLORS.border,
  },
  ivRow: { flexDirection: "row", alignItems: "center" },
  ivIcon: {
    width: 36, height: 36, borderRadius: 18,
    backgroundColor: "rgba(200,169,107,0.15)",
    alignItems: "center", justifyContent: "center", marginRight: 10,
  },
  ivActions: { flexDirection: "row", gap: 10, marginTop: 12 },
  btnGhost: {
    flex: 1,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1, borderColor: COLORS.error,
    backgroundColor: "rgba(248,113,113,0.06)",
  },
  btnAccept: {
    flex: 1,
    flexDirection: "row",
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: COLORS.accent,
  },
  slotInputRow: { flexDirection: "row", gap: 8, paddingHorizontal: 20, marginBottom: 12 },
  input: {
    flex: 1,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: COLORS.white,
    borderWidth: 1, borderColor: COLORS.border,
  },
  addBtn: {
    width: 46, height: 46, borderRadius: 12,
    backgroundColor: COLORS.accent,
    alignItems: "center", justifyContent: "center",
  },
  slotRow: {
    marginHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    backgroundColor: COLORS.bgSoft,
    borderRadius: 12,
    borderWidth: 1, borderColor: COLORS.border,
    marginBottom: 6,
  },
  oauthTeaser: {
    marginHorizontal: 20,
    marginTop: 16,
    padding: 14,
    backgroundColor: "rgba(200,169,107,0.05)",
    borderRadius: 14,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.2)",
  },
  oauthBtn: {
    alignSelf: "flex-start",
    marginTop: 10,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1, borderColor: "rgba(200,169,107,0.3)",
  },
});
