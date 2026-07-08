import { useCallback, useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Modal } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, EmptyState } from "@/src/components/ui";
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

const FILTERS = [
  { key: "all", label: "Tous" },
  { key: "ok", label: "OK" },
  { key: "attention", label: "Attention" },
  { key: "maintenance", label: "Maintenance" },
  { key: "replace", label: "À remplacer" },
];

export default function EquipmentList() {
  const { id, new: openNew } = useLocalSearchParams<{ id: string; new?: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api<any[]>(`/properties/${id}/equipment`);
      setItems(data);
    } catch {}
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  useEffect(() => { if (openNew === "1") setModalOpen(true); }, [openNew]);

  const filtered = filter === "all" ? items : items.filter((i) => i.status === filter);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Équipements</Txt>
        <Pressable testID="add-equipment-btn" onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}); setModalOpen(true); }} style={styles.iconBtn}>
          <Ionicons name="add" size={22} color={colors.brand} />
        </Pressable>
      </View>

      {/* Filters */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
        {FILTERS.map((f) => (
          <Pressable
            key={f.key}
            testID={`filter-${f.key}`}
            onPress={() => { Haptics.selectionAsync().catch(() => {}); setFilter(f.key); }}
            style={[styles.filterChip, filter === f.key && styles.filterChipActive]}
          >
            <Txt size="sm" weight="bold" color={filter === f.key ? colors.onSurfaceInverse : colors.onSurface}>{f.label}</Txt>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2, gap: spacing.md }}>
        {filtered.length === 0 ? (
          <EmptyState
            icon="cog"
            title={items.length === 0 ? "Aucun équipement" : "Aucun résultat pour ce filtre"}
            subtitle={items.length === 0 ? "Ajoutez chaudière, VMC, panneau électrique, panneaux solaires…" : undefined}
            ctaLabel={items.length === 0 ? "Ajouter un équipement" : undefined}
            onCta={items.length === 0 ? () => setModalOpen(true) : undefined}
            ctaTestID="empty-add-equipment"
          />
        ) : (
          filtered.map((e) => (
            <Pressable
              key={e.equipment_id}
              testID={`equipment-${e.equipment_id}`}
              onPress={() => router.push({ pathname: "/property/[id]/equipment/[eid]", params: { id, eid: e.equipment_id } })}
              style={({ pressed }) => [styles.equipRow, { transform: [{ scale: pressed ? 0.99 : 1 }] }]}
            >
              <View style={styles.equipIcon}>
                <Ionicons name={(CATEGORIES.find((c) => c.key === e.category) || CATEGORIES[13]).icon} size={22} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <Txt weight="bold" numberOfLines={1}>{e.name}</Txt>
                <Txt size="sm" color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>
                  {[e.brand, e.model].filter(Boolean).join(" • ") || "Sans marque"}
                </Txt>
                {!!e.warranty_until && (
                  <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
                    <Ionicons name="ribbon" size={12} color={colors.brand} />
                    <Txt size="sm" color={colors.brand} style={{ marginLeft: 4 }}>{`Garantie jusqu'au ${formatDate(e.warranty_until)}`}</Txt>
                  </View>
                )}
              </View>
              <View style={[styles.statusChip, { backgroundColor: (STATUSES.find((s) => s.key === e.status)?.color || colors.muted) + "22", borderColor: (STATUSES.find((s) => s.key === e.status)?.color || colors.muted) + "55" }]}>
                <View style={[styles.statusDot, { backgroundColor: STATUSES.find((s) => s.key === e.status)?.color || colors.muted }]} />
                <Txt size="sm" weight="bold" color={STATUSES.find((s) => s.key === e.status)?.color || colors.muted}>
                  {STATUSES.find((s) => s.key === e.status)?.label || e.status}
                </Txt>
              </View>
            </Pressable>
          ))
        )}
      </ScrollView>

      <EquipmentModal
        visible={modalOpen}
        onClose={() => setModalOpen(false)}
        propertyId={id!}
        onSaved={() => { setModalOpen(false); load(); }}
      />
    </View>
  );
}

function EquipmentModal({ visible, onClose, propertyId, onSaved }: { visible: boolean; onClose: () => void; propertyId: string; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("boiler");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [serial, setSerial] = useState("");
  const [installer, setInstaller] = useState("");
  const [installedOn, setInstalledOn] = useState("");
  const [warranty, setWarranty] = useState("");
  const [status, setStatus] = useState("ok");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (visible) {
      setName(""); setCategory("boiler"); setBrand(""); setModel(""); setSerial("");
      setInstaller(""); setInstalledOn(""); setWarranty(""); setStatus("ok"); setNotes("");
    }
  }, [visible]);

  const save = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await api(`/properties/${propertyId}/equipment`, {
        method: "POST",
        body: {
          name: name.trim(),
          category,
          brand: brand.trim(),
          model: model.trim(),
          serial_number: serial.trim(),
          installer: installer.trim(),
          installed_on: installedOn || null,
          warranty_until: warranty || null,
          status,
          notes: notes.trim(),
        },
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      onSaved();
    } catch {}
    setSaving(false);
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: colors.surface }}>
        <View style={styles.modalHeader}>
          <Pressable testID="modal-close" onPress={onClose} hitSlop={10}>
            <Txt weight="semibold" color={colors.muted}>Annuler</Txt>
          </Pressable>
          <Txt weight="bold" size="lg">Nouvel équipement</Txt>
          <Pressable testID="modal-save" onPress={save} disabled={!name.trim() || saving} hitSlop={10}>
            <Txt weight="bold" color={!name.trim() ? colors.muted : colors.brand}>{saving ? "…" : "Enregistrer"}</Txt>
          </Pressable>
        </View>

        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] }} keyboardShouldPersistTaps="handled">
            <FormLabel>Catégorie</FormLabel>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.lg }}>
              {CATEGORIES.map((c) => (
                <Pressable
                  key={c.key}
                  testID={`cat-${c.key}`}
                  onPress={() => { Haptics.selectionAsync().catch(() => {}); setCategory(c.key); }}
                  style={[styles.catChip, category === c.key && styles.catChipActive]}
                >
                  <Ionicons name={c.icon} size={16} color={category === c.key ? colors.onSurfaceInverse : colors.onSurface} />
                  <Txt size="sm" weight="bold" color={category === c.key ? colors.onSurfaceInverse : colors.onSurface} style={{ marginLeft: 6 }}>{c.label}</Txt>
                </Pressable>
              ))}
            </ScrollView>

            <FormLabel>Nom *</FormLabel>
            <TextInput testID="eq-name" value={name} onChangeText={setName} placeholder="Chaudière principale" placeholderTextColor={colors.muted} style={styles.input} />

            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <FormLabel>Marque</FormLabel>
                <TextInput testID="eq-brand" value={brand} onChangeText={setBrand} placeholder="De Dietrich" placeholderTextColor={colors.muted} style={styles.input} />
              </View>
              <View style={{ flex: 1 }}>
                <FormLabel>Modèle</FormLabel>
                <TextInput testID="eq-model" value={model} onChangeText={setModel} placeholder="Vivadens MCA 25" placeholderTextColor={colors.muted} style={styles.input} />
              </View>
            </View>

            <FormLabel>N° de série</FormLabel>
            <TextInput testID="eq-serial" value={serial} onChangeText={setSerial} placeholder="ABC-123456" placeholderTextColor={colors.muted} style={styles.input} />

            <FormLabel>Installateur</FormLabel>
            <TextInput testID="eq-installer" value={installer} onChangeText={setInstaller} placeholder="Nom de l'artisan" placeholderTextColor={colors.muted} style={styles.input} />

            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <View style={{ flex: 1 }}>
                <FormLabel>Installation</FormLabel>
                <TextInput testID="eq-installed" value={installedOn} onChangeText={setInstalledOn} placeholder="2024-05-12" placeholderTextColor={colors.muted} style={styles.input} />
              </View>
              <View style={{ flex: 1 }}>
                <FormLabel>Garantie</FormLabel>
                <TextInput testID="eq-warranty" value={warranty} onChangeText={setWarranty} placeholder="2029-05-12" placeholderTextColor={colors.muted} style={styles.input} />
              </View>
            </View>

            <FormLabel>Statut</FormLabel>
            <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
              {STATUSES.map((s) => (
                <Pressable
                  key={s.key}
                  testID={`st-${s.key}`}
                  onPress={() => { Haptics.selectionAsync().catch(() => {}); setStatus(s.key); }}
                  style={[styles.statusOption, status === s.key && { borderColor: s.color, backgroundColor: s.color + "22" }]}
                >
                  <View style={[styles.statusDot, { backgroundColor: s.color }]} />
                  <Txt size="sm" weight="bold" color={status === s.key ? s.color : colors.onSurface} style={{ marginLeft: 6 }}>{s.label}</Txt>
                </Pressable>
              ))}
            </View>

            <FormLabel>Notes</FormLabel>
            <TextInput testID="eq-notes" value={notes} onChangeText={setNotes} multiline placeholder="…" placeholderTextColor={colors.muted} style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: spacing.md }]} />
          </ScrollView>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

function FormLabel({ children }: { children: React.ReactNode }) {
  return (
    <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginTop: spacing.lg, marginBottom: spacing.sm, letterSpacing: 0.5 }}>
      {String(children).toUpperCase()}
    </Txt>
  );
}

function formatDate(iso?: string) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
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
  filterRow: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  filterChip: {
    height: 36, paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
    flexShrink: 0,
  },
  filterChipActive: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  equipRow: {
    flexDirection: "row", alignItems: "center",
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    gap: spacing.md,
  },
  equipIcon: {
    width: 48, height: 48, borderRadius: 12,
    backgroundColor: colors.brand + "18",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  statusChip: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  modalHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  catChip: {
    flexDirection: "row", alignItems: "center",
    height: 36, paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    flexShrink: 0,
  },
  catChipActive: {
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
  statusOption: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: 10,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
});
