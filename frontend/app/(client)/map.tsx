/**
 * Auxora V2 — Map placeholder (full-screen redesign coming in Phase D).
 */
import React from "react";
import { View, Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { Text, useTheme, space, palette } from "@/src/design";
import { hap } from "@/src/design/haptics";

export default function MapPlaceholder() {
  const t = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  return (
    <View style={{ flex: 1, backgroundColor: t.bg }}>
      <StatusBar style={t.scheme === "dark" ? "light" : "dark"} />
      <View style={{ flex: 1, paddingTop: insets.top + space.xxl, paddingHorizontal: space.xl }}>
        <Text variant="caption" tone="fgSubtle" style={{ color: palette.gold, letterSpacing: 3 }}>AUXORA</Text>
        <Text variant="display" style={{ marginTop: space.md, letterSpacing: -2 }}>Carte</Text>
        <Text variant="body" tone="fgMuted" style={{ marginTop: space.md, maxWidth: 320 }}>
          Bientôt disponible — un plan Uber pour trouver un artisan proche de vous en quelques secondes.
        </Text>
        <Pressable
          onPress={() => { hap.tap(); router.push("/(client)/"); }}
          style={{
            marginTop: space.xxxl, height: 52, borderRadius: 999,
            backgroundColor: t.fg, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: space.sm,
          }}
        >
          <Ionicons name="sparkles-outline" size={18} color={t.bg} />
          <Text variant="h3" style={{ color: t.bg }}>Demander à Auxora</Text>
        </Pressable>
      </View>
    </View>
  );
}
