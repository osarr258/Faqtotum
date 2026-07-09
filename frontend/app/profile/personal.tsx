import React, { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, Alert, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/AuthContext";
import { colors, radius, spacing } from "@/src/theme";

export default function PersonalInfo() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, refresh } = useAuth();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [postal, setPostal] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useFocusEffect(useCallback(() => {
    (async () => {
      try {
        const me = await api<any>("/auth/me");
        setName(me.name || ""); setPhone(me.phone || ""); setAddress(me.address || "");
        setCity(me.city || ""); setPostal(me.postal_code || "");
      } finally { setLoading(false); }
    })();
  }, []));

  const save = async () => {
    setBusy(true);
    try {
      await api("/users/me", { method: "PATCH", body: { name, phone, address, city, postal_code: postal } });
      await refresh();
      Alert.alert("Enregistré", "Vos informations ont été mises à jour.");
      router.back();
    } catch (e: any) { Alert.alert("Erreur", e?.message); }
    finally { setBusy(false); }
  };

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Informations</Txt>
        <View style={{ width: 32 }} />
      </View>

      <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
        <View>
          <Txt size="sm" color={colors.muted} style={{ marginBottom: 4 }}>Email</Txt>
          <View style={[styles.input, { backgroundColor: colors.surfaceTertiary }]}>
            <Txt style={{ color: colors.muted }}>{user?.email}</Txt>
          </View>
        </View>
        <Field label="Nom complet" value={name} onChangeText={setName} placeholder="Jean Dupont" />
        <Field label="Téléphone" value={phone} onChangeText={setPhone} placeholder="06 12 34 56 78" keyboardType="phone-pad" />
        <Field label="Adresse" value={address} onChangeText={setAddress} placeholder="12 rue de la Paix" />
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <View style={{ flex: 1 }}><Field label="Ville" value={city} onChangeText={setCity} placeholder="Paris" /></View>
          <View style={{ width: 110 }}><Field label="Code postal" value={postal} onChangeText={setPostal} placeholder="75001" keyboardType="number-pad" /></View>
        </View>

        <Pressable testID="save-profile" onPress={save} disabled={busy} style={({ pressed }) => [styles.primary, (busy || pressed) && { opacity: 0.85 }]}>
          {busy ? <ActivityIndicator color={colors.onBrand} /> : <Txt weight="bold" color={colors.onBrand}>Enregistrer</Txt>}
        </Pressable>
      </View>
    </ScrollView>
  );
}

function Field({ label, ...props }: any) {
  return (
    <View>
      <Txt size="sm" color={colors.muted} style={{ marginBottom: 4 }}>{label}</Txt>
      <TextInput {...props} placeholderTextColor={colors.muted} style={styles.input} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 16, borderWidth: 1, borderColor: colors.border },
  primary: { backgroundColor: colors.brand, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: "center", marginTop: spacing.md },
});
