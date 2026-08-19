/**
 * RequestCard — carte "demande" unifiée FAQTOTUM.
 *
 * Design minimaliste noir/blanc/gris. Zone URGENT proéminente en haut
 * (barre rouge + badge pulsant) SI la demande est marquée urgente.
 * Actions Accepter / Refuser affichées uniquement pour les demandes en
 * attente.
 */
import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Pressable, Animated, Easing } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing, font, fontSize } from "@/src/theme";

export type RequestData = {
  booking_id: string;
  client_name: string;
  trade_name?: string;
  date: string;
  slot: string;
  description?: string;
  urgent?: boolean;
  status: string;
};

type Props = {
  request: RequestData;
  onAccept?: (id: string) => void;
  onDecline?: (id: string) => void;
  onOpen?: (id: string) => void;
  compact?: boolean;
};

function UrgentPulse() {
  const pulse = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 0.35,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);
  return (
    <View style={styles.urgentBar}>
      <Animated.View style={[styles.urgentDot, { opacity: pulse }]} />
      <Txt
        weight="extrabold"
        size="sm"
        color={colors.textInverse}
        style={{ letterSpacing: 1.5 }}
      >
        URGENT
      </Txt>
    </View>
  );
}

export default function RequestCard({
  request,
  onAccept,
  onDecline,
  onOpen,
  compact,
}: Props) {
  const isPending = request.status === "pending";
  const initials = (request.client_name || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase())
    .join("");

  const handle = (fn?: (id: string) => void) => () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    fn?.(request.booking_id);
  };

  return (
    <Pressable
      testID={`request-${request.booking_id}`}
      onPress={handle(onOpen)}
      style={({ pressed }) => [
        styles.card,
        request.urgent && styles.cardUrgent,
        pressed && { opacity: 0.9 },
      ]}
    >
      {request.urgent ? <UrgentPulse /> : null}

      <View style={styles.body}>
        <View style={styles.headerRow}>
          <View style={styles.avatar}>
            <Txt weight="bold" size="sm">
              {initials || "?"}
            </Txt>
          </View>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="bold" size="lg">
              {request.client_name}
            </Txt>
            {request.trade_name ? (
              <Txt size="sm" color={colors.muted}>
                {request.trade_name}
              </Txt>
            ) : null}
          </View>
        </View>

        <View style={styles.metaRow}>
          <Ionicons name="calendar-outline" size={14} color={colors.muted} />
          <Txt size="sm" color={colors.muted} style={{ marginLeft: 6 }}>
            {request.date} · {request.slot}
          </Txt>
        </View>

        {!compact && request.description ? (
          <Txt
            size="sm"
            color={colors.onSurfaceTertiary}
            numberOfLines={2}
            style={{ marginTop: spacing.sm, lineHeight: 20 }}
          >
            {request.description}
          </Txt>
        ) : null}

        {isPending ? (
          <View style={styles.actions}>
            <Pressable
              testID={`decline-${request.booking_id}`}
              onPress={handle(onDecline)}
              style={({ pressed }) => [
                styles.btn,
                styles.btnGhost,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Txt weight="bold" size="sm">
                Refuser
              </Txt>
            </Pressable>
            <Pressable
              testID={`accept-${request.booking_id}`}
              onPress={handle(onAccept)}
              style={({ pressed }) => [
                styles.btn,
                styles.btnPrimary,
                pressed && { opacity: 0.85 },
              ]}
            >
              <Ionicons name="checkmark" size={16} color={colors.textInverse} />
              <Txt
                weight="bold"
                size="sm"
                color={colors.textInverse}
                style={{ marginLeft: 6 }}
              >
                Accepter
              </Txt>
            </Pressable>
          </View>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    marginBottom: spacing.md,
  },
  cardUrgent: {
    borderColor: colors.error,
    borderWidth: 1.5,
  },
  urgentBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.error,
    paddingHorizontal: spacing.lg,
    paddingVertical: 8,
    gap: 8,
  },
  urgentDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.textInverse,
  },
  body: {
    padding: spacing.lg,
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
  metaRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.md,
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  btn: {
    flex: 1,
    height: 44,
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

// Silence unused-var warnings from the shared tokens object.
void font;
void fontSize;
