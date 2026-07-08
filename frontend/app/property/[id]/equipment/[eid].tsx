import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Alert } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const CATEGORIES = [
  { key: "boiler", label: "Chaudière", icon: "flame" as const },
  { key: "water_heater", label: "Chauffe-eau", icon: "water" as const },
  { key: "heat_pump", label: "Pompe à chaleur", icon: "snow" as const },
  { key: "panel", label: "Tableau élec.", icon: "flash" as const },
  { key: "ac", label: "Climatiseur", icon: "snow" as const },
  { key: "vmc", label: "VMC", icon: "sync" as const },
  { key: "roof", label: "Toiture", icon: "home" as const },
  { key: "windows", label: "Fenêtres", icon: "square-outline" as const },
  { key: "doors", label: "Portes", icon: "log-in" as const },
  { key: "smoke_detector", label: "Détecteur", icon: "warning" as const },
  { key: "solar", label: "Solaire", icon: "sunny" as const },
  { key: "ev_charger", label: "Borne VE", icon: "battery-charging" as const },
  { key: "water_softener", label: "Adoucisseur", icon: "water" as const },
  { key: "other", label: "Autre", icon: "cog" as const },
];

const STATUSES = [
  { key: "ok", label: "OK", color: colors.success },
  { key: "attention", label: "Attention", color: colors.warning },
  { key: "maintenance", label: "Maintenance", color: colors.warning },
  { key: "replace", label: "À remplacer", color: colors.error },
];

export default function EquipmentDetail() {
  const { id, eid } = useLocalSearchParams<{ id: string; eid: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [e, setE] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<any>(`/properties/${id}/equipment/${eid}`);
      setE(data);
    } catch {}
  }, [id, eid]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const patch = (patchObj: any) => setE((prev: any) => ({ ...prev, ...patchObj }));

  const save = async () => {
    if (!e) return;
    setSaving(true);
    try {
      await api(`/properties/${id}/equipment/${eid}`, {
        method: "PATCH",
        body: {
          name: e.name || "",
          category: e.category || "other",
          brand: e.brand || "",
          model: e.model || "",
          serial_number: e.serial_number || "",
          installer: e.installer || "",
          installed_on: e.installed_on || null,
          warranty_until: e.warranty_until || null,
          status: e.status || "ok",
          notes: e.notes || "",
          photos: e.photos || [],
          documents: e.documents || [],
        },
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.back();
    } catch {}
    setSaving(false);
  };

  const removeEquipment = () => {
    Alert.alert("Supprimer l'équipement", "Cette action est irréversible.", [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: async () => {
        await api(`/properties/${id}/equipment/${eid}`, { method: "DELETE" });
        router.back();
      } },
    ]);
  };

  if (!e) {
    return <View style={{ flex: 1, backgroundColor: colors.surface }} />;
  }

  const cat = CATEGORIES.find((c) => c.key === e.category) || CATEGORIES[13];
  const stat = STATUSES.find((s) => s.key === e.status) || STATUSES[0];

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Équipement</Txt>
        <Pressable testID="delete-equipment-btn" onPress={removeEquipment} style={styles.iconBtn}>
          <Ionicons name="trash-outline" size={18} color={colors.error} />
        </Pressable>
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }} keyboardShouldPersistTaps="handled">
          <View style={styles.heroCard}>
            <LinearGradient colors={[colors.brand + "22", colors.surfaceSecondary]} style={StyleSheet.absoluteFillObject as any} />
            <View style={styles.heroIcon}>
              <Ionicons name={cat.icon} size={32} color={colors.brand} />
            </View>
            <Txt weight="extrabold" size="2xl" style={{ marginTop: spacing.md }}>{e.name || "Sans nom"}</Txt>
            <Txt color={colors.muted} size="sm" style={{ marginTop: 4 }}>{cat.label}</Txt>
            <View style={[styles.statusBadge, { backgroundColor: stat.color + "22", borderColor: stat.color + "55" }]}>
              <View style={[styles.statusDot, { backgroundColor: stat.color }]} />
              <Txt size="sm" weight="bold" color={stat.color} style={{ marginLeft: 6 }}>{stat.label}</Txt>
            </View>
          </View>

          <FormLabel>Nom</FormLabel>
          <TextInput testID="name" value={e.name || ""} onChangeText={(v) => patch({ name: v })} style={styles.input} placeholderTextColor={colors.muted} />

          <FormLabel>Catégorie</FormLabel>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.lg }}>
            {CATEGORIES.map((c) => (
              <Pressable
                key={c.key}
                testID={`cat-${c.key}`}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); patch({ category: c.key }); }}
                style={[styles.catChip, e.category === c.key && styles.catChipActive]}
              >
                <Ionicons name={c.icon} size={16} color={e.category === c.key ? colors.onSurfaceInverse : colors.onSurface} />
                <Txt size="sm" weight="bold" color={e.category === c.key ? colors.onSurfaceInverse : colors.onSurface} style={{ marginLeft: 6 }}>{c.label}</Txt>
              </Pressable>
            ))}
          </ScrollView>

          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <FormLabel>Marque</FormLabel>
              <TextInput testID="brand" value={e.brand || ""} onChangeText={(v) => patch({ brand: v })} style={styles.input} placeholderTextColor={colors.muted} />
            </View>
            <View style={{ flex: 1 }}>
              <FormLabel>Modèle</FormLabel>
              <TextInput testID="model" value={e.model || ""} onChangeText={(v) => patch({ model: v })} style={styles.input} placeholderTextColor={colors.muted} />
            </View>
          </View>

          <FormLabel>N° de série</FormLabel>
          <TextInput testID="serial" value={e.serial_number || ""} onChangeText={(v) => patch({ serial_number: v })} style={styles.input} placeholderTextColor={colors.muted} />

          <FormLabel>Installateur</FormLabel>
          <TextInput testID="installer" value={e.installer || ""} onChangeText={(v) => patch({ installer: v })} style={styles.input} placeholderTextColor={colors.muted} />

          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <FormLabel>Installation</FormLabel>
              <TextInput testID="installed" value={e.installed_on || ""} onChangeText={(v) => patch({ installed_on: v })} placeholder="AAAA-MM-JJ" placeholderTextColor={colors.muted} style={styles.input} />
            </View>
            <View style={{ flex: 1 }}>
              <FormLabel>Garantie</FormLabel>
              <TextInput testID="warranty" value={e.warranty_until || ""} onChangeText={(v) => patch({ warranty_until: v })} placeholder="AAAA-MM-JJ" placeholderTextColor={colors.muted} style={styles.input} />
            </View>
          </View>

          <FormLabel>Statut</FormLabel>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
            {STATUSES.map((s) => (
              <Pressable
                key={s.key}
                testID={`status-${s.key}`}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); patch({ status: s.key }); }}
                style={[styles.statusOption, e.status === s.key && { borderColor: s.color, backgroundColor: s.color + "22" }]}
              >
                <View style={[styles.statusDot, { backgroundColor: s.color }]} />
                <Txt size="sm" weight="bold" color={e.status === s.key ? s.color : colors.onSurface} style={{ marginLeft: 6 }}>{s.label}</Txt>
              </Pressable>
            ))}
          </View>

          <FormLabel>Notes</FormLabel>
          <TextInput testID="notes" value={e.notes || ""} onChangeText={(v) => patch({ notes: v })} multiline style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: spacing.md }]} placeholderTextColor={colors.muted} />

          <Button testID="save-btn" title="Enregistrer" onPress={save} loading={saving} style={{ marginTop: spacing.xl }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function FormLabel({ children }: { children: React.ReactNode }) {
  return (
    <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginTop: spacing.lg, marginBottom: spacing.sm, letterSpacing: 0.5 }}>
      {String(children).toUpperCase()}
    </Txt>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
  },
  heroCard: {
    padding: spacing.xl,
    borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
    alignItems: "flex-start",
  },
  heroIcon: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: colors.brand + "22",
    borderWidth: 1, borderColor: colors.brand + "55",
    alignItems: "center", justifyContent: "center",
  },
  statusBadge: {
    flexDirection: "row", alignItems: "center",
    marginTop: spacing.md,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  catChip: {
    flexDirection: "row", alignItems: "center",
    height: 36, paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    flexShrink: 0,
  },
  catChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  input: {
    height: 52,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    color: colors.onSurface,
    fontFamily: font.medium,
    fontSize: fontSize.lg,
  },
  statusOption: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
});
