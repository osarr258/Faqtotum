import { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, TextInput, Pressable, KeyboardAvoidingView, Platform } from "react-native";
import { Image } from "expo-image";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const TYPES = [
  { key: "apartment", label: "Appartement", icon: "business" as const },
  { key: "house", label: "Maison", icon: "home" as const },
  { key: "office", label: "Bureau", icon: "briefcase" as const },
  { key: "commercial", label: "Commerce", icon: "storefront" as const },
  { key: "vacation", label: "Secondaire", icon: "sunny" as const },
];

export default function PropertyCreateEdit() {
  const params = useLocalSearchParams<{ id?: string }>();
  const isEdit = !!params.id;
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [name, setName] = useState("");
  const [type, setType] = useState("apartment");
  const [address, setAddress] = useState("");
  const [surface, setSurface] = useState("");
  const [year, setYear] = useState("");
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const p = await api<any>(`/properties/${params.id}`);
        setName(p.name || "");
        setType(p.type || "apartment");
        setAddress(p.address || "");
        setSurface(p.surface != null ? String(p.surface) : "");
        setYear(p.year_built != null ? String(p.year_built) : "");
        setNotes(p.notes || "");
        setPhotos(p.photos || []);
      } catch {}
      setLoading(false);
    })();
  }, [isEdit, params.id]);

  const pickPhoto = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.7,
      base64: true,
      allowsMultipleSelection: false,
    });
    if (res.canceled || !res.assets?.[0]?.base64) return;
    const uri = `data:image/jpeg;base64,${res.assets[0].base64}`;
    setPhotos((prev) => [uri, ...prev]);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  };

  const removePhoto = (idx: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== idx));
  };

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const body = {
        name: name.trim(),
        type,
        address: address.trim(),
        surface: surface ? parseFloat(surface) : null,
        year_built: year ? parseInt(year, 10) : null,
        notes: notes.trim(),
        photos,
      };
      if (isEdit) {
        await api(`/properties/${params.id}`, { method: "PATCH", body });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        router.back();
      } else {
        const p = await api<any>("/properties", { method: "POST", body });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        router.replace({ pathname: "/property/[id]", params: { id: p.property_id } });
      }
    } catch {}
    setSaving(false);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>
          {isEdit ? "Modifier le bien" : "Nouveau bien"}
        </Txt>
        <View style={{ width: 40 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2 }} keyboardShouldPersistTaps="handled">
          <SectionTitle>Photo de couverture</SectionTitle>
          <View style={styles.photoRow}>
            {photos.slice(0, 4).map((uri, idx) => (
              <View key={idx} style={styles.photoThumb}>
                <Image source={{ uri }} style={{ width: "100%", height: "100%" }} contentFit="cover" />
                <Pressable testID={`remove-photo-${idx}`} onPress={() => removePhoto(idx)} style={styles.photoRemove}>
                  <Ionicons name="close" size={14} color="#fff" />
                </Pressable>
              </View>
            ))}
            {photos.length < 4 && (
              <Pressable testID="add-photo-btn" onPress={pickPhoto} style={styles.photoAdd}>
                <Ionicons name="camera" size={22} color={colors.brand} />
                <Txt size="sm" weight="semibold" color={colors.brand} style={{ marginTop: 4 }}>Ajouter</Txt>
              </Pressable>
            )}
          </View>

          <SectionTitle>Type de bien</SectionTitle>
          <View style={styles.typesWrap}>
            {TYPES.map((t) => (
              <Pressable
                key={t.key}
                testID={`type-${t.key}`}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); setType(t.key); }}
                style={[styles.typeChip, type === t.key && styles.typeChipActive]}
              >
                <Ionicons name={t.icon} size={16} color={type === t.key ? colors.onSurfaceInverse : colors.onSurface} />
                <Txt size="sm" weight="bold" color={type === t.key ? colors.onSurfaceInverse : colors.onSurface} style={{ marginLeft: 6 }}>{t.label}</Txt>
              </Pressable>
            ))}
          </View>

          <SectionTitle>Nom *</SectionTitle>
          <TextInput
            testID="name-input"
            value={name}
            onChangeText={setName}
            placeholder="Appartement Paris 11"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />

          <SectionTitle>Adresse</SectionTitle>
          <TextInput
            testID="address-input"
            value={address}
            onChangeText={setAddress}
            placeholder="12 rue de la Roquette, 75011"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />

          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <View style={{ flex: 1 }}>
              <SectionTitle>Surface (m²)</SectionTitle>
              <TextInput
                testID="surface-input"
                value={surface}
                onChangeText={setSurface}
                placeholder="58"
                placeholderTextColor={colors.muted}
                keyboardType="numeric"
                style={styles.input}
              />
            </View>
            <View style={{ flex: 1 }}>
              <SectionTitle>Année</SectionTitle>
              <TextInput
                testID="year-input"
                value={year}
                onChangeText={setYear}
                placeholder="1930"
                placeholderTextColor={colors.muted}
                keyboardType="numeric"
                style={styles.input}
              />
            </View>
          </View>

          <SectionTitle>Notes</SectionTitle>
          <TextInput
            testID="notes-input"
            value={notes}
            onChangeText={setNotes}
            placeholder="Charme haussmannien, 3e étage sans ascenseur…"
            placeholderTextColor={colors.muted}
            multiline
            style={[styles.input, { minHeight: 90, textAlignVertical: "top", paddingTop: spacing.md }]}
          />

          <Button
            testID="save-property-btn"
            title={isEdit ? "Enregistrer" : "Créer le bien"}
            loading={saving}
            disabled={!name.trim() || loading}
            onPress={save}
            style={{ marginTop: spacing.xl }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginBottom: spacing.sm, marginTop: spacing.lg, letterSpacing: 0.5 }}>
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
  photoRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  photoThumb: {
    width: 84, height: 84, borderRadius: radius.md,
    overflow: "hidden", backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    position: "relative",
  },
  photoAdd: {
    width: 84, height: 84, borderRadius: radius.md,
    backgroundColor: colors.brand + "12",
    borderWidth: 1, borderColor: colors.brand + "55",
    borderStyle: "dashed",
    alignItems: "center", justifyContent: "center",
  },
  photoRemove: {
    position: "absolute", top: 4, right: 4,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center", justifyContent: "center",
  },
  typesWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  typeChip: {
    flexDirection: "row", alignItems: "center",
    paddingVertical: 10, paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  typeChipActive: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
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
});
