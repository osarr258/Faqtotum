import { useCallback, useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Modal, Alert } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const CATEGORIES = [
  { key: "invoice", label: "Factures", icon: "receipt" as const },
  { key: "guarantee", label: "Garanties", icon: "ribbon" as const },
  { key: "manual", label: "Manuels", icon: "book" as const },
  { key: "certificate", label: "Certificats", icon: "shield-checkmark" as const },
  { key: "plan", label: "Plans", icon: "map" as const },
  { key: "photo", label: "Photos", icon: "images" as const },
  { key: "report", label: "Rapports", icon: "clipboard" as const },
  { key: "other", label: "Autres", icon: "document" as const },
];

export default function Documents() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api<any[]>(`/properties/${id}/documents`)); } catch {}
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = filter === "all" ? items : items.filter((i) => i.category === filter);

  const remove = (docId: string) => {
    Alert.alert("Supprimer ce document ?", "", [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: async () => {
        await api(`/properties/${id}/documents/${docId}`, { method: "DELETE" });
        load();
      } },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Documents</Txt>
        <Pressable testID="add-doc-btn" onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}); setOpen(true); }} style={styles.iconBtn}>
          <Ionicons name="add" size={22} color={colors.brand} />
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filterRow}>
        <Pressable testID="filter-all" onPress={() => { Haptics.selectionAsync().catch(() => {}); setFilter("all"); }} style={[styles.filterChip, filter === "all" && styles.filterChipActive]}>
          <Txt size="sm" weight="bold" color={filter === "all" ? colors.onSurfaceInverse : colors.onSurface}>Tous</Txt>
        </Pressable>
        {CATEGORIES.map((c) => (
          <Pressable key={c.key} testID={`filter-${c.key}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setFilter(c.key); }} style={[styles.filterChip, filter === c.key && styles.filterChipActive]}>
            <Ionicons name={c.icon} size={14} color={filter === c.key ? colors.onSurfaceInverse : colors.onSurface} />
            <Txt size="sm" weight="bold" color={filter === c.key ? colors.onSurfaceInverse : colors.onSurface} style={{ marginLeft: 4 }}>{c.label}</Txt>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2, gap: spacing.md }}>
        {filtered.length === 0 ? (
          <EmptyState
            icon="documents"
            title={items.length === 0 ? "Passeport numérique vide" : "Aucun document dans cette catégorie"}
            subtitle={items.length === 0 ? "Chaque facture, garantie et rapport signé chez vous restera ici." : undefined}
            ctaLabel={items.length === 0 ? "Ajouter un document" : undefined}
            onCta={items.length === 0 ? () => setOpen(true) : undefined}
            ctaTestID="empty-add-doc"
          />
        ) : (
          filtered.map((d) => {
            const c = CATEGORIES.find((x) => x.key === d.category) || CATEGORIES[7];
            return (
              <Pressable
                key={d.document_id}
                testID={`doc-${d.document_id}`}
                onLongPress={() => remove(d.document_id)}
                style={styles.row}
              >
                <View style={styles.docIcon}><Ionicons name={c.icon} size={22} color={colors.brand} /></View>
                <View style={{ flex: 1 }}>
                  <Txt weight="bold" numberOfLines={1}>{d.title}</Txt>
                  <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>{c.label} • {formatDate(d.created_at)}</Txt>
                </View>
                <Pressable testID={`del-doc-${d.document_id}`} onPress={() => remove(d.document_id)} hitSlop={10}>
                  <Ionicons name="ellipsis-horizontal" size={20} color={colors.muted} />
                </Pressable>
              </Pressable>
            );
          })
        )}
      </ScrollView>

      <DocModal visible={open} onClose={() => setOpen(false)} propertyId={id!} onSaved={() => { setOpen(false); load(); }} />
    </View>
  );
}

function DocModal({ visible, onClose, propertyId, onSaved }: { visible: boolean; onClose: () => void; propertyId: string; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("invoice");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (visible) { setTitle(""); setCategory("invoice"); setNotes(""); } }, [visible]);
  const save = async () => {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await api(`/properties/${propertyId}/documents`, {
        method: "POST",
        body: { title: title.trim(), category, notes: notes.trim() },
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
          <Pressable testID="mclose" onPress={onClose} hitSlop={10}><Txt color={colors.muted} weight="semibold">Annuler</Txt></Pressable>
          <Txt weight="bold" size="lg">Nouveau document</Txt>
          <Pressable testID="msave" onPress={save} disabled={!title.trim() || saving} hitSlop={10}><Txt weight="bold" color={!title.trim() ? colors.muted : colors.brand}>{saving ? "…" : "Enregistrer"}</Txt></Pressable>
        </View>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }} keyboardShouldPersistTaps="handled">
            <FormLabel>Titre *</FormLabel>
            <TextInput testID="doc-title" value={title} onChangeText={setTitle} placeholder="Facture chaudière 2024" placeholderTextColor={colors.muted} style={styles.input} />
            <FormLabel>Catégorie</FormLabel>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.lg }}>
              {CATEGORIES.map((c) => (
                <Pressable key={c.key} testID={`docat-${c.key}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setCategory(c.key); }} style={[styles.catChip, category === c.key && styles.catChipActive]}>
                  <Ionicons name={c.icon} size={16} color={category === c.key ? colors.onSurfaceInverse : colors.onSurface} />
                  <Txt size="sm" weight="bold" color={category === c.key ? colors.onSurfaceInverse : colors.onSurface} style={{ marginLeft: 6 }}>{c.label}</Txt>
                </Pressable>
              ))}
            </ScrollView>
            <FormLabel>Notes</FormLabel>
            <TextInput testID="doc-notes" value={notes} onChangeText={setNotes} multiline style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: spacing.md }]} placeholderTextColor={colors.muted} />
          </ScrollView>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

function FormLabel({ children }: { children: React.ReactNode }) {
  return <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginTop: spacing.lg, marginBottom: spacing.sm, letterSpacing: 0.5 }}>{String(children).toUpperCase()}</Txt>;
}
function formatDate(iso?: string) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  filterRow: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  filterChip: { flexDirection: "row", alignItems: "center", height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  filterChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  docIcon: { width: 48, height: 48, borderRadius: 12, backgroundColor: colors.brand + "18", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brand + "44" },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  catChip: { flexDirection: "row", alignItems: "center", height: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, flexShrink: 0 },
  catChipActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  input: { minHeight: 52, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, color: colors.onSurface, fontFamily: font.medium, fontSize: fontSize.lg },
});
