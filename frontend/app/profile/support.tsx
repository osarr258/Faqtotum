import React from "react";
import { View, StyleSheet, ScrollView, Pressable, Linking, Alert } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { colors, radius, spacing } from "@/src/theme";

export default function Support() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const openMail = () => Linking.openURL("mailto:support@auxora.fr?subject=Support%20Auxora").catch(() => Alert.alert("Email", "support@auxora.fr"));
  const openWhatsapp = () => Linking.openURL("https://wa.me/33600000000").catch(() => Alert.alert("WhatsApp", "+33 6 00 00 00 00"));

  const items = [
    { icon: "chatbubbles", label: "Discuter avec Auxora IA", sub: "Réponse instantanée 24/7", onPress: () => router.replace("/") },
    { icon: "mail", label: "Contacter par email", sub: "support@auxora.fr", onPress: openMail },
    { icon: "logo-whatsapp", label: "WhatsApp", sub: "Réponse sous 1h en journée", onPress: openWhatsapp },
    { icon: "help-buoy", label: "Centre d'aide", sub: "FAQ et guides", onPress: () => Alert.alert("Centre d'aide", "Disponible très bientôt.") },
    { icon: "document-text", label: "Conditions d'utilisation", sub: "Version 1.0", onPress: () => Linking.openURL("https://auxora.fr/cgu").catch(() => {}) },
    { icon: "lock-closed", label: "Politique de confidentialité", sub: "RGPD", onPress: () => Linking.openURL("https://auxora.fr/privacy").catch(() => {}) },
  ] as const;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Aide & support</Txt>
        <View style={{ width: 32 }} />
      </View>

      <View style={styles.group}>
        {items.map((it, i) => (
          <Pressable key={it.label} testID={`support-${i}`} onPress={it.onPress} style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }, i < items.length - 1 && styles.rowBorder]}>
            <View style={styles.iconWrap}>
              <Ionicons name={it.icon as any} size={18} color={colors.brand} />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="semibold">{it.label}</Txt>
              <Txt size="sm" color={colors.muted}>{it.sub}</Txt>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        ))}
      </View>

      <View style={styles.versionBox}>
        <Txt size="sm" color={colors.muted}>Auxora — version 1.0.0</Txt>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, minHeight: 68 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconWrap: { width: 36, height: 36, borderRadius: 18, backgroundColor: `${colors.brand}18`, alignItems: "center", justifyContent: "center" },
  versionBox: { alignItems: "center", marginTop: spacing.xl },
});
