/**
 * Reserve — Réservation classique FAQTOTUM V1 (brief §11).
 *
 * Écran client dédié : sélection date + créneau + description →
 * poste un broadcast NON urgent avec l'estimation IA optionnelle,
 * puis redirige vers /broadcast/{id}.
 */
import { useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import FaqtotumLogo from "@/src/components/FaqtotumLogo";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const SLOTS = [
  "08:00-10:00", "10:00-12:00", "14:00-16:00", "16:00-18:00", "18:00-20:00",
];

function nextDays(n: number): { iso: string; label: string; day: string }[] {
  const arr: { iso: string; label: string; day: string }[] = [];
  const dayLabels = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];
  const now = new Date();
  for (let i = 0; i < n; i++) {
    const d = new Date(now);
    d.setDate(d.getDate() + i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    arr.push({
      iso: `${y}-${m}-${day}`,
      label: String(d.getDate()),
      day: dayLabels[d.getDay()],
    });
  }
  return arr;
}

export default function Reserve() {
  const router = useRouter();
  const params = useLocalSearchParams<{ trade?: string; description?: string }>();
  const insets = useSafeAreaInsets();
  const days = nextDays(14);
  const [trade, setTrade] = useState(params.trade || "plombier");
  const [date, setDate] = useState(days[1].iso);
  const [slot, setSlot] = useState(SLOTS[2]);
  const [description, setDescription] = useState(params.description || "");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!description.trim()) {
      Alert.alert("Description requise", "Décrivez brièvement votre besoin.");
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    setSubmitting(true);
    try {
      const bc = await api<{ broadcast_id: string }>("/broadcasts", {
        method: "POST",
        body: {
          trade,
          date,
          slot,
          description,
          urgent: false,
        },
      });
      router.replace({
        pathname: "/broadcast/[id]",
        params: { id: bc.broadcast_id },
      });
    } catch (e) {
      const s = e instanceof Error ? e.message : "Erreur";
      Alert.alert("Erreur", s);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: colors.surface }}
    >
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable
          testID="close-btn"
          onPress={() => router.back()}
          style={styles.iconBtn}
          hitSlop={10}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={styles.logoRow}>
          <FaqtotumLogo size={20} color={colors.brand} />
          <Txt weight="bold" size="sm" style={{ marginLeft: 6 }}>
            faqtotum
          </Txt>
        </View>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }}
        keyboardShouldPersistTaps="handled"
      >
        <Txt size="sm" color={colors.muted}>
          Réservation
        </Txt>
        <Txt weight="extrabold" size="3xl" style={{ marginTop: 2 }}>
          Réserver un créneau
        </Txt>

        <Txt
          weight="bold"
          size="sm"
          color={colors.muted}
          style={{ marginTop: spacing.xl, marginBottom: spacing.sm, letterSpacing: 1 }}
        >
          DATE
        </Txt>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: spacing.sm }}
        >
          {days.map((d) => {
            const active = d.iso === date;
            return (
              <Pressable
                key={d.iso}
                testID={`day-${d.iso}`}
                onPress={() => {
                  Haptics.selectionAsync().catch(() => {});
                  setDate(d.iso);
                }}
                style={[styles.dayCell, active && styles.dayCellActive]}
              >
                <Txt
                  size="sm"
                  color={active ? colors.textInverse : colors.muted}
                >
                  {d.day}
                </Txt>
                <Txt
                  weight="extrabold"
                  size="lg"
                  color={active ? colors.textInverse : colors.onSurface}
                  style={{ marginTop: 2 }}
                >
                  {d.label}
                </Txt>
              </Pressable>
            );
          })}
        </ScrollView>

        <Txt
          weight="bold"
          size="sm"
          color={colors.muted}
          style={{ marginTop: spacing.xl, marginBottom: spacing.sm, letterSpacing: 1 }}
        >
          CRÉNEAU
        </Txt>
        <View style={styles.slotsGrid}>
          {SLOTS.map((s) => {
            const active = s === slot;
            return (
              <Pressable
                key={s}
                testID={`slot-${s}`}
                onPress={() => {
                  Haptics.selectionAsync().catch(() => {});
                  setSlot(s);
                }}
                style={[styles.slotCell, active && styles.slotCellActive]}
              >
                <Txt
                  weight="bold"
                  size="sm"
                  color={active ? colors.textInverse : colors.onSurface}
                >
                  {s}
                </Txt>
              </Pressable>
            );
          })}
        </View>

        <Txt
          weight="bold"
          size="sm"
          color={colors.muted}
          style={{ marginTop: spacing.xl, marginBottom: spacing.sm, letterSpacing: 1 }}
        >
          MÉTIER
        </Txt>
        <View style={styles.slotsGrid}>
          {["plombier", "electricien", "chauffagiste", "serrurier", "peintre", "menuisier"].map(
            (t) => {
              const active = t === trade;
              return (
                <Pressable
                  key={t}
                  testID={`trade-${t}`}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setTrade(t);
                  }}
                  style={[styles.slotCell, active && styles.slotCellActive]}
                >
                  <Txt
                    weight="bold"
                    size="sm"
                    color={active ? colors.textInverse : colors.onSurface}
                  >
                    {t}
                  </Txt>
                </Pressable>
              );
            },
          )}
        </View>

        <Txt
          weight="bold"
          size="sm"
          color={colors.muted}
          style={{ marginTop: spacing.xl, marginBottom: spacing.sm, letterSpacing: 1 }}
        >
          VOTRE BESOIN
        </Txt>
        <TextInput
          testID="desc-input"
          value={description}
          onChangeText={setDescription}
          placeholder="Décrivez brièvement votre problème…"
          placeholderTextColor={colors.muted}
          multiline
          style={styles.input}
        />
      </ScrollView>

      <View
        style={[
          styles.footer,
          { paddingBottom: insets.bottom + spacing.md },
        ]}
      >
        <Button
          testID="submit-reservation"
          title="Chercher un artisan"
          onPress={submit}
          loading={submitting}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  logoRow: { flexDirection: "row", alignItems: "center" },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  dayCell: {
    minWidth: 62,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
  },
  dayCellActive: { backgroundColor: colors.brand },
  slotsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  slotCell: {
    paddingHorizontal: spacing.md,
    height: 40,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceSecondary,
  },
  slotCellActive: { backgroundColor: colors.brand },
  input: {
    minHeight: 110,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    padding: spacing.md,
    fontFamily: font.medium,
    fontSize: fontSize.base,
    color: colors.onSurface,
    textAlignVertical: "top",
  },
  footer: {
    padding: spacing.lg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
});
