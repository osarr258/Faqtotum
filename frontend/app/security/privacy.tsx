import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Switch, Alert, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/AuthContext";
import { colors, radius, spacing } from "@/src/theme";

type Consents = { marketing: boolean; analytics: boolean; third_party: boolean };

export default function PrivacyScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { logout } = useAuth();
  const [consents, setConsents] = useState<Consents>({ marketing: false, analytics: false, third_party: false });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useFocusEffect(useCallback(() => {
    (async () => {
      try {
        const r = await api<Consents>("/security/gdpr/consents");
        setConsents({ marketing: !!r.marketing, analytics: !!r.analytics, third_party: !!r.third_party });
      } finally { setLoading(false); }
    })();
  }, []));

  const update = async (patch: Partial<Consents>) => {
    const nx = { ...consents, ...patch };
    setConsents(nx); setSaving(true);
    try { await api("/security/gdpr/consents", { method: "POST", body: nx }); }
    catch (e: any) { Alert.alert("Erreur", e.message); }
    finally { setSaving(false); }
  };

  const exportData = async () => {
    try {
      const data = await api("/security/gdpr/export");
      Alert.alert(
        "Export généré",
        `Données exportées : ${Object.keys(data.collections || {}).length} collection(s). Un e-mail contenant le fichier vous sera envoyé.`
      );
    } catch (e: any) { Alert.alert("Erreur", e.message); }
  };

  const deleteAccount = () => {
    Alert.alert(
      "⚠️ Supprimer définitivement votre compte ?",
      "Vos données personnelles seront anonymisées. Les logs légaux seront conservés 30 jours puis supprimés. Cette action est irréversible.",
      [
        { text: "Annuler", style: "cancel" },
        {
          text: "Supprimer", style: "destructive", onPress: async () => {
            try {
              await api("/security/gdpr/account", { method: "DELETE" });
              Alert.alert("Compte supprimé", "Vos données ont été anonymisées.");
              await logout();
              router.replace("/onboarding");
            } catch (e: any) { Alert.alert("Erreur", e.message); }
          }
        },
      ]
    );
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Confidentialité (RGPD)</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <>
          <Txt weight="bold" size="base" style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.md }}>Consentements</Txt>
          <View style={styles.group}>
            {([
              { key: "marketing", label: "E-mails marketing", sub: "Recevoir des offres et actualités" },
              { key: "analytics", label: "Analytiques anonymisées", sub: "Aider à améliorer l'app" },
              { key: "third_party", label: "Partage avec partenaires", sub: "Uniquement partenaires vérifiés" },
            ] as const).map((c, i, arr) => (
              <View key={c.key} style={[styles.row, i < arr.length - 1 && styles.rowBorder]}>
                <View style={{ flex: 1 }}>
                  <Txt weight="semibold" size="base">{c.label}</Txt>
                  <Txt color={colors.muted} size="sm">{c.sub}</Txt>
                </View>
                <Switch
                  testID={`consent-${c.key}`}
                  value={consents[c.key]}
                  onValueChange={(v) => update({ [c.key]: v } as any)}
                  trackColor={{ true: colors.brand, false: colors.surfaceTertiary }}
                  thumbColor={colors.onSurface}
                  disabled={saving}
                />
              </View>
            ))}
          </View>

          <Txt weight="bold" size="base" style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl, marginBottom: spacing.md }}>
            Vos droits RGPD
          </Txt>
          <View style={styles.group}>
            <Pressable testID="export-data" onPress={exportData} style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }, styles.rowBorder]}>
              <View style={styles.rowIcon}>
                <Ionicons name="download-outline" size={20} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <Txt weight="semibold" size="base">Exporter mes données</Txt>
                <Txt color={colors.muted} size="sm">Recevez un JSON complet de vos données</Txt>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>

            <Pressable testID="delete-account" onPress={deleteAccount} style={({ pressed }) => [styles.row, { opacity: pressed ? 0.6 : 1 }]}>
              <View style={styles.rowIcon}>
                <Ionicons name="trash-outline" size={20} color={colors.error} />
              </View>
              <View style={{ flex: 1 }}>
                <Txt weight="semibold" size="base" color={colors.error}>Supprimer mon compte</Txt>
                <Txt color={colors.muted} size="sm">Anonymisation immédiate — irréversible</Txt>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          </View>

          <View style={styles.legalBox}>
            <Ionicons name="information-circle-outline" size={16} color={colors.muted} />
            <Txt size="sm" color={colors.muted} style={{ flex: 1, marginLeft: spacing.sm, lineHeight: 18 }}>
              Conforme RGPD. Les logs légaux sont conservés 30 jours après suppression, puis purgés automatiquement.
            </Txt>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  group: { marginHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minHeight: 64 },
  rowIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  legalBox: { flexDirection: "row", marginHorizontal: spacing.lg, marginTop: spacing.xl, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
});
