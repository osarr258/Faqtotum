import React from "react";
import { Text, Pressable, View, ActivityIndicator, StyleSheet, TextProps, PressableProps } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

export function Txt({ style, weight = "regular", size = "base", color = colors.onSurface, ...p }: TextProps & { weight?: keyof typeof font; size?: keyof typeof fontSize; color?: string }) {
  return <Text {...p} style={[{ fontFamily: font[weight], fontSize: fontSize[size], color }, style]} />;
}

type BtnProps = PressableProps & {
  title: string;
  variant?: "primary" | "secondary" | "outline";
  loading?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  testID?: string;
};

export function Button({ title, variant = "primary", loading, icon, onPress, disabled, testID, style }: BtnProps) {
  const bg = variant === "primary" ? colors.brand : variant === "secondary" ? colors.surfaceSecondary : "transparent";
  const fg = variant === "primary" ? colors.onSurfaceInverse : colors.onSurface;
  const handle = (e: any) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    onPress?.(e);
  };
  return (
    <Pressable
      testID={testID}
      onPress={handle}
      disabled={disabled || loading}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1, borderWidth: variant === "outline" ? 1.5 : 0, borderColor: colors.borderStrong },
        style as any,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <View style={styles.btnRow}>
          {icon && <Ionicons name={icon} size={18} color={fg} style={{ marginRight: spacing.sm }} />}
          <Text style={{ fontFamily: font.bold, fontSize: fontSize.lg, color: fg }}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
}

export function Avatar({ name, uri, size = 48 }: { name?: string; uri?: string | null; size?: number }) {
  const initials = (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  if (uri) {
    return (
      <View style={{ width: size, height: size, borderRadius: size / 2, overflow: "hidden", backgroundColor: colors.surfaceTertiary }}>
        <Image source={{ uri }} style={{ width: "100%", height: "100%" }} contentFit="cover" transition={150} />
      </View>
    );
  }
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center" }}>
      <Text style={{ fontFamily: font.bold, color: colors.onSurfaceInverse, fontSize: size * 0.36 }}>{initials}</Text>
    </View>
  );
}

export function Rating({ value, count }: { value: number; count?: number }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center" }}>
      <Ionicons name="star" size={14} color={colors.star} />
      <Txt weight="semibold" size="sm" style={{ marginLeft: 4 }}>{value?.toFixed(1)}</Txt>
      {count != null && <Txt size="sm" color={colors.muted} style={{ marginLeft: 4 }}>({count})</Txt>}
    </View>
  );
}

export function EmptyState({ icon, title, subtitle }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle?: string }) {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyIcon}>
        <Ionicons name={icon} size={32} color={colors.muted} />
      </View>
      <Txt weight="bold" size="lg" style={{ marginTop: spacing.lg, textAlign: "center" }}>{title}</Txt>
      {subtitle && <Txt color={colors.muted} style={{ marginTop: spacing.xs, textAlign: "center" }}>{subtitle}</Txt>}
    </View>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    pending: { label: "En attente", color: colors.warning, bg: "#FEF3C7" },
    accepted: { label: "Acceptée", color: colors.success, bg: "#D1FAE5" },
    declined: { label: "Refusée", color: colors.error, bg: "#FEE2E2" },
    completed: { label: "Terminée", color: colors.onSurfaceTertiary, bg: colors.surfaceSecondary },
  };
  const s = map[status] || map.pending;
  return (
    <View style={{ backgroundColor: s.bg, paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill }}>
      <Text style={{ fontFamily: font.semibold, fontSize: fontSize.sm, color: s.color }}>{s.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  btn: { height: 54, borderRadius: radius.md, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  btnRow: { flexDirection: "row", alignItems: "center" },
  empty: { alignItems: "center", justifyContent: "center", paddingVertical: spacing["3xl"], paddingHorizontal: spacing.xl },
  emptyIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
});
