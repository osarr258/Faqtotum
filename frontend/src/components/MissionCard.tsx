/**
 * MissionCard — carte mission FAQTOTUM avec statut vivant.
 *
 * Utilisée dans l'onglet Missions (segment "En cours" et "Historique").
 * Contrairement à RequestCard, MissionCard n'a pas d'action rapide
 * accepter/refuser — la mission est déjà engagée. Les actions dépendent
 * du statut courant (démarrer, terminer, voir détail, chat).
 */
import React from "react";
import { View, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

export type MissionData = {
  id: string;
  kind: "booking" | "intervention";
  client_name: string;
  trade_name?: string;
  date?: string;
  slot?: string;
  description?: string;
  status: string;
  urgent?: boolean;
  amount_cents?: number;
};

type Action = {
  label: string;
  onPress: () => void;
  variant?: "primary" | "ghost";
  icon?: keyof typeof Ionicons.glyphMap;
  testID?: string;
};

type Props = {
  mission: MissionData;
  onOpen?: (m: MissionData) => void;
  actions?: Action[];
};

const STATUS_LABEL: Record<string, string> = {
  pending: "En attente",
  assigned: "Assignée",
  accepted: "Confirmée",
  confirmed: "Confirmée",
  professional_on_the_way: "En route",
  en_route: "En route",
  arrived: "Sur place",
  in_progress: "En cours",
  awaiting_validation: "À valider",
  completed: "Terminée",
  validated: "Validée",
  declined: "Refusée",
  cancelled: "Annulée",
  disputed: "Litige",
};

const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  pending: { bg: colors.surfaceSecondary, fg: colors.onSurface },
  assigned: { bg: colors.surfaceSecondary, fg: colors.onSurface },
  accepted: { bg: colors.brand, fg: colors.textInverse },
  confirmed: { bg: colors.brand, fg: colors.textInverse },
  en_route: { bg: colors.brand, fg: colors.textInverse },
  professional_on_the_way: { bg: colors.brand, fg: colors.textInverse },
  arrived: { bg: colors.brand, fg: colors.textInverse },
  in_progress: { bg: colors.brand, fg: colors.textInverse },
  awaiting_validation: { bg: colors.warning, fg: "#442200" },
  completed: { bg: "#D1FAE5", fg: "#065F46" },
  validated: { bg: "#D1FAE5", fg: "#065F46" },
  declined: { bg: colors.surfaceSecondary, fg: colors.muted },
  cancelled: { bg: colors.surfaceSecondary, fg: colors.muted },
  disputed: { bg: "#FEE2E2", fg: "#991B1B" },
};

export default function MissionCard({ mission, onOpen, actions }: Props) {
  const initials = (mission.client_name || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");
  const label = STATUS_LABEL[mission.status] || mission.status;
  const st = STATUS_STYLE[mission.status] || {
    bg: colors.surfaceSecondary,
    fg: colors.onSurface,
  };

  const wrap = (fn: () => void) => () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    fn();
  };

  return (
    <Pressable
      testID={`mission-${mission.id}`}
      onPress={onOpen ? wrap(() => onOpen(mission)) : undefined}
      style={({ pressed }) => [
        styles.card,
        mission.urgent && styles.cardUrgent,
        pressed && { opacity: 0.9 },
      ]}
    >
      <View style={styles.headerRow}>
        <View style={styles.avatar}>
          <Txt weight="bold" size="sm">
            {initials || "?"}
          </Txt>
        </View>
        <View style={{ flex: 1, marginLeft: spacing.md }}>
          <Txt weight="bold" size="lg">
            {mission.client_name}
          </Txt>
          {mission.trade_name ? (
            <Txt size="sm" color={colors.muted}>
              {mission.trade_name}
            </Txt>
          ) : null}
        </View>
        <View style={[styles.statusPill, { backgroundColor: st.bg }]}>
          <Txt weight="bold" size="sm" color={st.fg}>
            {label}
          </Txt>
        </View>
      </View>

      {mission.date || mission.slot ? (
        <View style={styles.metaRow}>
          <Ionicons name="calendar-outline" size={14} color={colors.muted} />
          <Txt size="sm" color={colors.muted} style={{ marginLeft: 6 }}>
            {mission.date}
            {mission.slot ? ` · ${mission.slot}` : ""}
          </Txt>
        </View>
      ) : null}

      {mission.description ? (
        <Txt
          size="sm"
          color={colors.onSurfaceTertiary}
          numberOfLines={2}
          style={{ marginTop: spacing.sm, lineHeight: 20 }}
        >
          {mission.description}
        </Txt>
      ) : null}

      {mission.amount_cents ? (
        <View style={styles.amountRow}>
          <Txt size="sm" color={colors.muted}>
            Montant
          </Txt>
          <Txt weight="extrabold" size="lg">
            {(mission.amount_cents / 100).toFixed(2)} €
          </Txt>
        </View>
      ) : null}

      {actions && actions.length > 0 ? (
        <View style={styles.actions}>
          {actions.map((a, i) => (
            <Pressable
              key={i}
              testID={a.testID}
              onPress={wrap(a.onPress)}
              style={({ pressed }) => [
                styles.btn,
                a.variant === "primary" ? styles.btnPrimary : styles.btnGhost,
                pressed && { opacity: 0.8 },
              ]}
            >
              {a.icon ? (
                <Ionicons
                  name={a.icon}
                  size={14}
                  color={
                    a.variant === "primary"
                      ? colors.textInverse
                      : colors.onSurface
                  }
                />
              ) : null}
              <Txt
                weight="bold"
                size="sm"
                color={
                  a.variant === "primary"
                    ? colors.textInverse
                    : colors.onSurface
                }
                style={a.icon ? { marginLeft: 6 } : undefined}
              >
                {a.label}
              </Txt>
            </Pressable>
          ))}
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardUrgent: {
    borderColor: colors.error,
    borderWidth: 1.5,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  avatar: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  statusPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.md,
  },
  amountRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  btn: {
    flex: 1,
    height: 42,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
  },
  btnGhost: {
    backgroundColor: colors.surfaceSecondary,
  },
  btnPrimary: {
    backgroundColor: colors.brand,
  },
});
