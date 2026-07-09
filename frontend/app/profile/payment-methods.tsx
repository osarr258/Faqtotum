import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Alert, ActivityIndicator, Platform } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

type PM = { pm_id: string; brand: string; last4: string; exp_month?: number; exp_year?: number; is_default: boolean };

export default function PaymentMethods() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [methods, setMethods] = useState<PM[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api<{ methods: PM[] }>("/users/me/payment-methods");
      setMethods(r.methods);
    } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const addFake = async (brand: string) => {
    const last4 = String(Math.floor(1000 + Math.random() * 9000));
    try {
      await api("/users/me/payment-methods", { method: "POST", body: { brand, last4, exp_month: 12, exp_year: 2029, is_default: methods.length === 0 } });
      load();
    } catch (e: any) { Alert.alert("Erreur", e?.message); }
  };

  const setDefault = async (pm_id: string) => {
    await api(`/users/me/payment-methods/${pm_id}/default`, { method: "POST" });
    load();
  };

  const remove = async (pm_id: string) => {
    Alert.alert("Supprimer ?", "Cette carte sera supprimée.", [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: async () => { await api(`/users/me/payment-methods/${pm_id}`, { method: "DELETE" }); load(); } },
    ]);
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Moyens de paiement</Txt>
        <View style={{ width: 32 }} />
      </View>

      {loading ? (
        <ActivityIndicator color={colors.brand} style={{ marginTop: 40 }} />
      ) : (
        <>
          {methods.length === 0 && (
            <Txt color={colors.muted} style={{ textAlign: "center", paddingHorizontal: spacing.lg, marginTop: spacing.md }}>
              Aucune carte enregistrée. Vos paiements Apple Pay & carte fonctionnent directement.
            </Txt>
          )}

          {methods.map((m) => (
            <View key={m.pm_id} style={styles.card}>
              <View style={styles.brandIcon}>
                <Ionicons name={m.brand === "apple_pay" ? "logo-apple" : "card"} size={22} color={colors.brand} />
              </View>
              <View style={{ flex: 1, marginLeft: spacing.md }}>
                <Txt weight="bold">{m.brand.toUpperCase()} •••• {m.last4}</Txt>
                {m.exp_month && <Txt size="sm" color={colors.muted}>Exp. {m.exp_month}/{m.exp_year}</Txt>}
                {m.is_default && <Txt size="sm" color={colors.brand} weight="bold" style={{ marginTop: 2 }}>Par défaut</Txt>}
              </View>
              {!m.is_default && (
                <Pressable onPress={() => setDefault(m.pm_id)} hitSlop={6} style={{ marginRight: 8 }}>
                  <Txt size="sm" color={colors.brand}>Définir</Txt>
                </Pressable>
              )}
              <Pressable onPress={() => remove(m.pm_id)} hitSlop={6}>
                <Ionicons name="trash-outline" size={18} color={colors.error} />
              </Pressable>
            </View>
          ))}

          <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg, gap: spacing.sm }}>
            <Txt weight="bold" size="sm" color={colors.muted}>AJOUTER</Txt>
            {Platform.OS === "ios" && (
              <Pressable testID="add-apple" onPress={() => addFake("apple_pay")} style={styles.addBtn}>
                <Ionicons name="logo-apple" size={18} color={colors.onSurface} />
                <Txt weight="semibold" style={{ marginLeft: spacing.sm }}>Apple Pay</Txt>
              </Pressable>
            )}
            <Pressable testID="add-card" onPress={() => addFake("visa")} style={styles.addBtn}>
              <Ionicons name="card" size={18} color={colors.onSurface} />
              <Txt weight="semibold" style={{ marginLeft: spacing.sm }}>Ajouter une carte</Txt>
            </Pressable>
          </View>

          <View style={styles.noticeBox}>
            <Ionicons name="information-circle-outline" size={16} color={colors.brand} />
            <Txt size="sm" color={colors.muted} style={{ marginLeft: spacing.sm, flex: 1, lineHeight: 18 }}>
              Mode démo — vos vraies cartes se connecteront via Stripe sur l&apos;app native (Apple Pay/Google Pay natif).
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
  card: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.sm },
  brandIcon: { width: 42, height: 42, borderRadius: 12, backgroundColor: `${colors.brand}18`, alignItems: "center", justifyContent: "center" },
  addBtn: { flexDirection: "row", alignItems: "center", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  noticeBox: { flexDirection: "row", marginHorizontal: spacing.lg, marginTop: spacing.lg, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
});
