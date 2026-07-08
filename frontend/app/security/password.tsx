import React, { useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, Alert, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

export default function PasswordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (next !== confirm) return Alert.alert("Erreur", "Les mots de passe ne correspondent pas.");
    if (next.length < 8) return Alert.alert("Erreur", "Au moins 8 caractères.");
    setBusy(true);
    try {
      await api("/security/password/change", { method: "POST", body: { current_password: current, new_password: next } });
      Alert.alert("Succès", "Mot de passe modifié.");
      router.back();
    } catch (e: any) { Alert.alert("Erreur", e.message); }
    finally { setBusy(false); }
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: spacing["3xl"] }}>
      <View style={styles.header}>
        <Pressable testID="back-btn" onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Txt weight="extrabold" size="xl">Mot de passe</Txt>
        <View style={{ width: 32 }} />
      </View>

      <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
        <View>
          <Txt size="sm" color={colors.muted} style={{ marginBottom: spacing.xs }}>Mot de passe actuel</Txt>
          <TextInput testID="current-pw" value={current} onChangeText={setCurrent} secureTextEntry placeholderTextColor={colors.muted} style={styles.input} />
        </View>
        <View>
          <Txt size="sm" color={colors.muted} style={{ marginBottom: spacing.xs }}>Nouveau mot de passe</Txt>
          <TextInput testID="new-pw" value={next} onChangeText={setNext} secureTextEntry placeholderTextColor={colors.muted} style={styles.input} />
        </View>
        <View>
          <Txt size="sm" color={colors.muted} style={{ marginBottom: spacing.xs }}>Confirmer</Txt>
          <TextInput testID="confirm-pw" value={confirm} onChangeText={setConfirm} secureTextEntry placeholderTextColor={colors.muted} style={styles.input} />
        </View>

        <View style={styles.hintBox}>
          <Ionicons name="information-circle-outline" size={16} color={colors.brand} />
          <Txt size="sm" color={colors.muted} style={{ flex: 1, marginLeft: spacing.sm, lineHeight: 18 }}>
            Minimum 8 caractères. Recommandation : mixer majuscules, chiffres et symboles.
          </Txt>
        </View>

        <Pressable testID="submit-pw" onPress={submit} disabled={busy} style={[styles.primary, busy && { opacity: 0.5 }]}>
          <Txt weight="bold" color={colors.onBrand}>Modifier</Txt>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 16, borderWidth: 1, borderColor: colors.border },
  hintBox: { flexDirection: "row", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  primary: { backgroundColor: colors.brand, paddingVertical: spacing.md, borderRadius: radius.md, alignItems: "center", marginTop: spacing.md },
});
