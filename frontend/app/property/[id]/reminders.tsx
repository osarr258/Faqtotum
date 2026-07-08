import { useCallback, useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, TextInput, KeyboardAvoidingView, Platform, Modal, Alert } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { Txt, EmptyState } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

const FREQUENCIES = [
  { key: "once", label: "Une fois" },
  { key: "monthly", label: "Mensuel" },
  { key: "quarterly", label: "Trimestriel" },
  { key: "biannual", label: "Semestriel" },
  { key: "yearly", label: "Annuel" },
];

const SUGGESTIONS = [
  "Entretien chaudière",
  "Inspection pompe à chaleur",
  "Batterie détecteur de fumée",
  "Inspection toiture",
  "Filtre à eau",
  "Contrôle VMC",
];

export default function Reminders() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await api<any[]>(`/properties/${id}/reminders`)); } catch {}
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const markDone = async (rid: string) => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    await api(`/properties/${id}/reminders/${rid}`, { method: "PATCH", body: { status: "done" } });
    load();
  };

  const remove = (rid: string) => {
    Alert.alert("Supprimer ce rappel ?", "", [
      { text: "Annuler", style: "cancel" },
      { text: "Supprimer", style: "destructive", onPress: async () => { await api(`/properties/${id}/reminders/${rid}`, { method: "DELETE" }); load(); } },
    ]);
  };

  const active = items.filter((r) => r.status === "upcoming" || r.status === "due");
  const done = items.filter((r) => r.status === "done");

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Txt weight="bold" size="lg" style={{ flex: 1, textAlign: "center" }}>Rappels</Txt>
        <Pressable testID="add-reminder-btn" onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}); setOpen(true); }} style={styles.iconBtn}>
          <Ionicons name="add" size={22} color={colors.brand} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["3xl"] * 2, gap: spacing.md }}>
        <View style={styles.futureNote}>
          <Ionicons name="notifications" size={18} color={colors.brand} />
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Txt weight="bold" size="sm">Notifications bientôt disponibles</Txt>
            <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
              Vous recevrez une notification à chaque échéance.
            </Txt>
          </View>
        </View>

        {items.length === 0 ? (
          <EmptyState
            icon="notifications"
            title="Aucun rappel"
            subtitle="Programmez vos entretiens : chaudière, VMC, détecteurs, toiture…"
            ctaLabel="Créer un rappel"
            onCta={() => setOpen(true)}
            ctaTestID="empty-add-reminder"
          />
        ) : (
          <>
            {active.length > 0 && (
              <>
                <SectionLabel>À VENIR</SectionLabel>
                {active.map((r) => (
                  <View key={r.reminder_id} style={styles.row}>
                    <View style={[styles.dot, r.status === "due" ? { backgroundColor: colors.warning } : { backgroundColor: colors.brand }]} />
                    <View style={{ flex: 1 }}>
                      <Txt weight="bold">{r.title}</Txt>
                      <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                        {r.status === "due" ? "En retard • " : "Échéance "}{formatDate(r.due_on)}{r.frequency ? ` • ${FREQUENCIES.find((f) => f.key === r.frequency)?.label || r.frequency}` : ""}
                      </Txt>
                    </View>
                    <Pressable testID={`done-${r.reminder_id}`} onPress={() => markDone(r.reminder_id)} style={styles.doneBtn}>
                      <Ionicons name="checkmark" size={16} color={colors.success} />
                    </Pressable>
                    <Pressable testID={`rm-${r.reminder_id}`} onPress={() => remove(r.reminder_id)} hitSlop={10} style={{ marginLeft: 6 }}>
                      <Ionicons name="ellipsis-horizontal" size={20} color={colors.muted} />
                    </Pressable>
                  </View>
                ))}
              </>
            )}
            {done.length > 0 && (
              <>
                <SectionLabel>TERMINÉS</SectionLabel>
                {done.map((r) => (
                  <View key={r.reminder_id} style={[styles.row, { opacity: 0.6 }]}>
                    <Ionicons name="checkmark-circle" size={18} color={colors.success} />
                    <View style={{ flex: 1, marginLeft: spacing.md }}>
                      <Txt weight="semibold" style={{ textDecorationLine: "line-through" }}>{r.title}</Txt>
                      <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>Terminé</Txt>
                    </View>
                    <Pressable testID={`rm-done-${r.reminder_id}`} onPress={() => remove(r.reminder_id)} hitSlop={10}>
                      <Ionicons name="trash-outline" size={16} color={colors.muted} />
                    </Pressable>
                  </View>
                ))}
              </>
            )}
          </>
        )}
      </ScrollView>

      <ReminderModal visible={open} onClose={() => setOpen(false)} propertyId={id!} onSaved={() => { setOpen(false); load(); }} />
    </View>
  );
}

function ReminderModal({ visible, onClose, propertyId, onSaved }: { visible: boolean; onClose: () => void; propertyId: string; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [dueOn, setDueOn] = useState("");
  const [freq, setFreq] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (visible) { setTitle(""); setDueOn(""); setFreq(null); setNotes(""); } }, [visible]);
  const save = async () => {
    if (!title.trim() || !dueOn.trim()) return;
    setSaving(true);
    try {
      await api(`/properties/${propertyId}/reminders`, {
        method: "POST",
        body: { title: title.trim(), due_on: dueOn.trim(), frequency: freq, notes: notes.trim() },
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
          <Txt weight="bold" size="lg">Nouveau rappel</Txt>
          <Pressable testID="msave" onPress={save} disabled={!title.trim() || !dueOn.trim() || saving} hitSlop={10}>
            <Txt weight="bold" color={!title.trim() || !dueOn.trim() ? colors.muted : colors.brand}>{saving ? "…" : "Enregistrer"}</Txt>
          </Pressable>
        </View>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }} keyboardShouldPersistTaps="handled">
            <FormLabel>Titre *</FormLabel>
            <TextInput testID="rem-title" value={title} onChangeText={setTitle} placeholder="Entretien chaudière" placeholderTextColor={colors.muted} style={styles.input} />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm, marginTop: spacing.sm, paddingRight: spacing.lg }}>
              {SUGGESTIONS.map((s) => (
                <Pressable key={s} testID={`sug-${s}`} onPress={() => { Haptics.selectionAsync().catch(() => {}); setTitle(s); }} style={styles.suggestion}>
                  <Txt size="sm" color={colors.brand}>{s}</Txt>
                </Pressable>
              ))}
            </ScrollView>

            <FormLabel>Échéance * (AAAA-MM-JJ)</FormLabel>
            <TextInput testID="rem-date" value={dueOn} onChangeText={setDueOn} placeholder="2026-11-15" placeholderTextColor={colors.muted} style={styles.input} />

            <FormLabel>Fréquence</FormLabel>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {FREQUENCIES.map((f) => (
                <Pressable
                  key={f.key}
                  testID={`freq-${f.key}`}
                  onPress={() => { Haptics.selectionAsync().catch(() => {}); setFreq((prev) => prev === f.key ? null : f.key); }}
                  style={[styles.freq, freq === f.key && styles.freqActive]}
                >
                  <Txt size="sm" weight="bold" color={freq === f.key ? colors.onSurfaceInverse : colors.onSurface}>{f.label}</Txt>
                </Pressable>
              ))}
            </View>

            <FormLabel>Notes</FormLabel>
            <TextInput testID="rem-notes" value={notes} onChangeText={setNotes} multiline style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: spacing.md }]} placeholderTextColor={colors.muted} />
          </ScrollView>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <Txt color={colors.muted} size="sm" weight="semibold" style={{ marginTop: spacing.lg, letterSpacing: 0.5 }}>{children}</Txt>;
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
  futureNote: { flexDirection: "row", alignItems: "center", padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brand + "0F", borderWidth: 1, borderColor: colors.brand + "33" },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  dot: { width: 10, height: 10, borderRadius: 5 },
  doneBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: colors.success + "22", borderWidth: 1, borderColor: colors.success + "55", alignItems: "center", justifyContent: "center" },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  suggestion: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brand + "14", borderWidth: 1, borderColor: colors.brand + "44", flexShrink: 0 },
  freq: { paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  freqActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  input: { minHeight: 52, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md, color: colors.onSurface, fontFamily: font.medium, fontSize: fontSize.lg },
});
