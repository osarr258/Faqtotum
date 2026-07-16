import { useCallback, useState } from "react";
import { View, StyleSheet, ScrollView, Pressable, RefreshControl, Modal, Share } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import * as Clipboard from "expo-clipboard";
import { Txt, Button } from "@/src/components/ui";
import { api } from "@/src/api";
import { colors, radius, spacing, shadow } from "@/src/theme";

type Property = {
  property_id: string;
  name: string;
  type: string;
  address?: string;
  city?: string;
  postal_code?: string;
  rooms?: number;
  dpe_grade?: string;
  cover_color?: string;
  share_token?: string | null;
  photos?: string[];
  surface?: number;
  year_built?: number;
  notes?: string;
};
type AiCard = { key: string; title: string; subtitle: string; icon: keyof typeof Ionicons.glyphMap; status: string };
type Insights = {
  equipment_count: number;
  equipment_ok: number;
  equipment_attention: number;
  document_count: number;
  upcoming_maintenance: number;
  interventions: number;
  money_invested: number;
  average_health: number;
  demo_values: boolean;
};

const TYPE_LABEL: Record<string, string> = {
  apartment: "Appartement",
  house: "Maison",
  office: "Bureau",
  commercial: "Commerce",
  vacation: "Résidence secondaire",
};

// Fallback trade-themed cover images bundled with the app (from the prototype)
const TYPE_HERO_FALLBACK: Record<string, any> = {
  apartment: require("@/assets/images/hero-peintre.jpg"),
  house: require("@/assets/images/hero-couvreur.jpg"),
  office: require("@/assets/images/hero-electricien.jpg"),
  commercial: require("@/assets/images/hero-menuisier.jpg"),
  vacation: require("@/assets/images/hero-plombier.jpg"),
};

export default function PropertyDashboard() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [prop, setProp] = useState<Property | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [aiCards, setAiCards] = useState<AiCard[]>([]);
  const [reminders, setReminders] = useState<any[]>([]);
  const [equipment, setEquipment] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, ins, ai, rem, eq] = await Promise.all([
        api<Property>(`/properties/${id}`),
        api<Insights>(`/properties/${id}/insights`),
        api<AiCard[]>(`/properties/${id}/ai-cards`),
        api<any[]>(`/properties/${id}/reminders`),
        api<any[]>(`/properties/${id}/equipment`),
      ]);
      setProp(p);
      setInsights(ins);
      setAiCards(ai);
      setReminders(rem);
      setEquipment(eq);
    } catch {}
  }, [id]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const cover = prop?.photos && prop.photos.length > 0 ? prop.photos[0] : null;
  const upcoming = reminders.filter((r) => r.status === "upcoming" || r.status === "due").slice(0, 3);
  const recentEquipment = equipment.slice(0, 3);

  const go = (path: string) => {
    Haptics.selectionAsync().catch(() => {});
    router.push(path as any);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: spacing["3xl"] * 2 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brand} />}
      >
        {/* Hero */}
        <View style={styles.hero}>
          {cover ? (
            <Image source={{ uri: cover }} style={StyleSheet.absoluteFillObject as any} contentFit="cover" transition={250} />
          ) : (
            <>
              <Image
                source={TYPE_HERO_FALLBACK[prop?.type || "apartment"]}
                style={StyleSheet.absoluteFillObject as any}
                contentFit="cover"
                transition={200}
              />
              <LinearGradient
                colors={[(prop?.cover_color || "#0EA5E9") + "80", "transparent"]}
                style={StyleSheet.absoluteFillObject as any}
              />
            </>
          )}
          <LinearGradient
            colors={["rgba(11,11,15,0.55)", "rgba(11,11,15,0.15)", "rgba(11,11,15,0.95)"]}
            style={StyleSheet.absoluteFillObject as any}
          />
          <View style={[styles.heroTop, { paddingTop: insets.top + spacing.sm }]}>
            <Pressable testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
              <Ionicons name="chevron-back" size={22} color="#fff" />
            </Pressable>
            <View style={{ flex: 1 }} />
            <Pressable
              testID="passport-btn"
              onPress={() => setShareOpen(true)}
              style={[styles.iconBtn, { paddingHorizontal: 12, flexDirection: "row", width: "auto", gap: 6 }]}
            >
              <Ionicons name="share-social" size={16} color="#fff" />
              <Txt size="sm" weight="bold" style={{ color: "#fff" }}>Passeport</Txt>
            </Pressable>
            <Pressable
              testID="edit-property-btn"
              onPress={() => router.push({ pathname: "/property/create", params: { id } })}
              style={styles.iconBtn}
            >
              <Ionicons name="create-outline" size={18} color="#fff" />
            </Pressable>
          </View>
          <View style={styles.heroBottom}>
            {prop && (
              <View style={styles.typeChip}>
                <Txt size="sm" weight="semibold" color={colors.brand}>{TYPE_LABEL[prop.type] || prop.type}</Txt>
              </View>
            )}
            <Txt weight="extrabold" size="3xl" style={{ color: "#fff", marginTop: spacing.sm }}>{prop?.name || "…"}</Txt>
            {(!!prop?.address || !!prop?.city) && (
              <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
                <Ionicons name="location" size={14} color="#D4D4DA" />
                <Txt size="sm" color="#D4D4DA" style={{ marginLeft: 4 }}>
                  {[prop?.address, prop?.postal_code, prop?.city].filter(Boolean).join(" · ")}
                </Txt>
              </View>
            )}
            {(!!prop?.surface || !!prop?.year_built || !!prop?.rooms || !!prop?.dpe_grade) && (
              <View style={{ flexDirection: "row", marginTop: spacing.md, gap: spacing.md, flexWrap: "wrap" }}>
                {!!prop?.surface && <MetaChip icon="resize" label={`${prop.surface} m²`} />}
                {!!prop?.year_built && <MetaChip icon="time" label={`${prop.year_built}`} />}
                {!!prop?.rooms && <MetaChip icon="grid" label={`${prop.rooms} pièces`} />}
                {!!prop?.dpe_grade && <MetaChip icon="leaf" label={`DPE ${prop.dpe_grade}`} />}
              </View>
            )}
          </View>
        </View>

        {/* Quick actions */}
        <View style={styles.quickWrap}>
          <QuickAction icon="cog" label="Équipements" count={insights?.equipment_count} onPress={() => go(`/property/${id}/equipment`)} testID="quick-equipment" />
          <QuickAction icon="document-text" label="Documents" count={insights?.document_count} onPress={() => go(`/property/${id}/documents`)} testID="quick-documents" />
          <QuickAction icon="stats-chart" label="Budget" onPress={() => go(`/property/${id}/budget`)} testID="quick-budget" />
          <QuickAction icon="notifications" label="Rappels" count={insights?.upcoming_maintenance} highlight={(insights?.upcoming_maintenance || 0) > 0} onPress={() => go(`/property/${id}/reminders`)} testID="quick-reminders" />
        </View>

        {/* Insights summary */}
        {insights && (
          <Pressable
            testID="insights-card"
            onPress={() => go(`/property/${id}/insights`)}
            style={({ pressed }) => [styles.insightsCard, { transform: [{ scale: pressed ? 0.99 : 1 }] }, shadow.card]}
          >
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md }}>
              <View>
                <Txt color={colors.muted} size="sm" weight="semibold" style={{ letterSpacing: 0.5 }}>SANTÉ DU BIEN</Txt>
                <Txt weight="extrabold" size="3xl" style={{ marginTop: 2 }}>{insights.average_health}%</Txt>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Ionicons name="pulse" size={26} color={colors.brand} />
                <Txt size="sm" color={colors.muted} style={{ marginTop: 4 }}>Voir tout</Txt>
              </View>
            </View>
            <View style={styles.healthBar}>
              <View style={[styles.healthFill, { width: `${insights.average_health}%` }]} />
            </View>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.md }}>
              <InlineStat label="Interventions" value={insights.interventions} />
              <InlineStat label="Investi" value={`${insights.money_invested.toLocaleString("fr-FR")} €`} />
              <InlineStat label="À prévoir" value={insights.upcoming_maintenance} highlight={insights.upcoming_maintenance > 0} />
            </View>
          </Pressable>
        )}

        {/* Upcoming reminders */}
        <SectionHeader title="Entretiens à venir" onSeeAll={() => go(`/property/${id}/reminders`)} seeAllTestID="see-all-reminders" />
        {upcoming.length === 0 ? (
          <View style={styles.emptyMini}>
            <Ionicons name="checkmark-circle" size={18} color={colors.success} />
            <Txt color={colors.muted} style={{ marginLeft: spacing.sm }}>Aucun entretien programmé.</Txt>
          </View>
        ) : (
          <View style={{ paddingHorizontal: spacing.lg, gap: spacing.sm }}>
            {upcoming.map((r) => (
              <View key={r.reminder_id} style={styles.reminderRow}>
                <View style={[styles.reminderDot, r.status === "due" && { backgroundColor: colors.warning }]} />
                <View style={{ flex: 1 }}>
                  <Txt weight="bold">{r.title}</Txt>
                  <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>Échéance {formatDate(r.due_on)}</Txt>
                </View>
                <View style={[styles.statusPill, r.status === "due" ? styles.statusPillDue : styles.statusPillUp]}>
                  <Txt size="sm" weight="semibold" color={r.status === "due" ? colors.warning : colors.brand}>
                    {r.status === "due" ? "En retard" : "À venir"}
                  </Txt>
                </View>
              </View>
            ))}
          </View>
        )}

        {/* Equipment preview */}
        <SectionHeader title="Équipements récents" onSeeAll={() => go(`/property/${id}/equipment`)} seeAllTestID="see-all-equipment" />
        {recentEquipment.length === 0 ? (
          <View style={styles.emptyEquip}>
            <View style={styles.emptyEquipIcon}><Ionicons name="cog" size={22} color={colors.brand} /></View>
            <View style={{ flex: 1 }}>
              <Txt weight="bold">Aucun équipement</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>Ajoutez chaudière, VMC, panneaux…</Txt>
            </View>
            <Pressable testID="add-first-equipment" onPress={() => go(`/property/${id}/equipment?new=1`)} style={styles.addChip}>
              <Ionicons name="add" size={16} color={colors.brand} />
              <Txt size="sm" weight="bold" color={colors.brand} style={{ marginLeft: 4 }}>Ajouter</Txt>
            </Pressable>
          </View>
        ) : (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
            {recentEquipment.map((e) => (
              <Pressable
                key={e.equipment_id}
                testID={`equipment-card-${e.equipment_id}`}
                onPress={() => go(`/property/${id}/equipment/${e.equipment_id}`)}
                style={styles.equipCard}
              >
                <View style={styles.equipIcon}><Ionicons name={equipIcon(e.category)} size={22} color={colors.brand} /></View>
                <Txt weight="bold" numberOfLines={1} style={{ marginTop: spacing.sm }}>{e.name}</Txt>
                <Txt size="sm" color={colors.muted} numberOfLines={1} style={{ marginTop: 2 }}>{e.brand || "—"}</Txt>
                <View style={[styles.statusDot, { backgroundColor: statusColor(e.status) }]} />
              </Pressable>
            ))}
          </ScrollView>
        )}

        {/* AI cards */}
        <SectionHeader title="Intelligence artificielle" subtitle="Bientôt disponible" />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {aiCards.map((c) => (
            <View key={c.key} style={styles.aiCard} testID={`ai-card-${c.key}`}>
              <View style={styles.aiIcon}>
                <Ionicons name={c.icon} size={20} color={colors.brand} />
              </View>
              <View style={styles.soonPill}>
                <Txt size="sm" weight="bold" color={colors.brand}>BIENTÔT</Txt>
              </View>
              <Txt weight="bold" size="lg" style={{ marginTop: spacing.md }}>{c.title}</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: spacing.xs, lineHeight: 18 }} numberOfLines={3}>{c.subtitle}</Txt>
            </View>
          ))}
        </ScrollView>

        {!!prop?.notes && (
          <>
            <SectionHeader title="Notes" />
            <View style={{ paddingHorizontal: spacing.lg }}>
              <View style={styles.notesCard}>
                <Txt style={{ lineHeight: 22 }} color={colors.onSurfaceSecondary}>{prop.notes}</Txt>
              </View>
            </View>
          </>
        )}

        <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.xl }}>
          <Button
            testID="report-problem-btn"
            title="Signaler un problème sur ce bien"
            variant="secondary"
            icon="alert-circle"
            onPress={() => router.push("/diagnose")}
          />
        </View>
      </ScrollView>

      {prop && (
        <PassportShareModal
          visible={shareOpen}
          onClose={() => setShareOpen(false)}
          property={prop}
          onUpdated={(token) => setProp({ ...prop, share_token: token })}
        />
      )}
    </View>
  );
}

function PassportShareModal({
  visible,
  onClose,
  property,
  onUpdated,
}: {
  visible: boolean;
  onClose: () => void;
  property: Property;
  onUpdated: (token: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const platformUrl = (process.env.EXPO_BACKEND_URL || "https://reviens-app.preview.emergentagent.com").replace(/\/$/, "");
  const url = property.share_token ? `${platformUrl}/passport/${property.share_token}` : null;

  const enable = async () => {
    setBusy(true);
    try {
      const res = await api<{ token: string; url: string }>(`/properties/${property.property_id}/share`, {
        method: "POST",
        body: {},
      });
      onUpdated(res.token);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch {}
    setBusy(false);
  };

  const revoke = async () => {
    setBusy(true);
    try {
      await api(`/properties/${property.property_id}/share`, { method: "DELETE" });
      onUpdated(null);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
    } catch {}
    setBusy(false);
  };

  const copy = async () => {
    if (!url) return;
    await Clipboard.setStringAsync(url);
    setCopied(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setTimeout(() => setCopied(false), 1500);
  };

  const shareNative = async () => {
    if (!url) return;
    try {
      await Share.share({
        message: `Passeport du logement "${property.name}" · Auxora\n${url}`,
        url,
      });
    } catch {}
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={shareStyles.backdrop}>
        <View style={shareStyles.sheet}>
          <View style={shareStyles.handle} />
          <View style={{ paddingHorizontal: spacing.lg }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.xs }}>
              <View style={shareStyles.icon}>
                <Ionicons name="qr-code" size={22} color={colors.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <Txt weight="extrabold" size="lg">Passeport numérique</Txt>
                <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                  Lien public en lecture seule — idéal pour un acheteur, un notaire ou un locataire.
                </Txt>
              </View>
              <Pressable onPress={onClose} hitSlop={12} style={shareStyles.close}>
                <Ionicons name="close" size={18} color={colors.onSurface} />
              </Pressable>
            </View>

            {!url ? (
              <>
                <View style={shareStyles.infoRow}>
                  <Ionicons name="shield-checkmark" size={16} color={colors.brand} />
                  <Txt size="sm" color={colors.muted} style={{ flex: 1, marginLeft: 8 }}>
                    Identité, équipements et historique visibles. Les documents restent privés.
                  </Txt>
                </View>
                <Button
                  testID="passport-enable-btn"
                  title="Générer un lien de partage"
                  icon="share-social"
                  loading={busy}
                  onPress={enable}
                  style={{ marginTop: spacing.lg }}
                />
              </>
            ) : (
              <>
                <View style={shareStyles.linkBox}>
                  <Txt size="sm" color={colors.muted} style={{ marginBottom: 4, letterSpacing: 0.4 }}>LIEN PUBLIC</Txt>
                  <Txt size="sm" weight="semibold" numberOfLines={2} style={{ lineHeight: 20 }}>{url}</Txt>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                  <Pressable
                    testID="passport-copy-btn"
                    onPress={copy}
                    style={({ pressed }) => [shareStyles.actionBtn, { flex: 1 }, pressed && { opacity: 0.85 }]}
                  >
                    <Ionicons name={copied ? "checkmark" : "copy"} size={16} color={colors.onSurface} />
                    <Txt weight="bold" style={{ marginLeft: 8 }}>{copied ? "Copié" : "Copier"}</Txt>
                  </Pressable>
                  <Pressable
                    testID="passport-share-btn"
                    onPress={shareNative}
                    style={({ pressed }) => [shareStyles.actionBtnPrimary, { flex: 1 }, pressed && { opacity: 0.85 }]}
                  >
                    <Ionicons name="share-outline" size={16} color="#fff" />
                    <Txt weight="bold" style={{ marginLeft: 8, color: "#fff" }}>Partager</Txt>
                  </Pressable>
                </View>
                <Pressable
                  testID="passport-revoke-btn"
                  onPress={revoke}
                  disabled={busy}
                  style={({ pressed }) => [shareStyles.revokeBtn, pressed && { opacity: 0.85 }]}
                >
                  <Ionicons name="trash" size={14} color={colors.error} />
                  <Txt size="sm" weight="bold" style={{ marginLeft: 6, color: colors.error }}>Révoquer le lien</Txt>
                </Pressable>
              </>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}

function MetaChip({ icon, label }: { icon: keyof typeof Ionicons.glyphMap; label: string }) {
  return (
    <View style={styles.metaChip}>
      <Ionicons name={icon} size={12} color="#fff" />
      <Txt size="sm" weight="semibold" style={{ color: "#fff", marginLeft: 4 }}>{label}</Txt>
    </View>
  );
}

function QuickAction({ icon, label, count, onPress, highlight, testID }: { icon: keyof typeof Ionicons.glyphMap; label: string; count?: number; onPress: () => void; highlight?: boolean; testID: string }) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.quickCard, { transform: [{ scale: pressed ? 0.96 : 1 }] }]}
    >
      <View style={[styles.quickIcon, highlight && { backgroundColor: colors.warning + "22", borderColor: colors.warning + "55" }]}>
        <Ionicons name={icon} size={20} color={highlight ? colors.warning : colors.brand} />
      </View>
      <Txt size="sm" weight="bold" style={{ marginTop: spacing.sm }}>{label}</Txt>
      {typeof count === "number" && <Txt size="sm" color={colors.muted}>{count}</Txt>}
    </Pressable>
  );
}

function InlineStat({ label, value, highlight }: { label: string; value: any; highlight?: boolean }) {
  return (
    <View>
      <Txt size="sm" color={colors.muted}>{label}</Txt>
      <Txt weight="extrabold" size="lg" style={{ marginTop: 2 }} color={highlight ? colors.warning : colors.onSurface}>{value}</Txt>
    </View>
  );
}

function SectionHeader({ title, subtitle, onSeeAll, seeAllTestID }: { title: string; subtitle?: string; onSeeAll?: () => void; seeAllTestID?: string }) {
  return (
    <View style={styles.sectionHeader}>
      <View style={{ flex: 1 }}>
        <Txt weight="extrabold" size="lg">{title}</Txt>
        {!!subtitle && <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>{subtitle}</Txt>}
      </View>
      {onSeeAll && (
        <Pressable testID={seeAllTestID} onPress={onSeeAll} hitSlop={12}>
          <Txt size="sm" weight="bold" color={colors.brand}>Tout voir</Txt>
        </Pressable>
      )}
    </View>
  );
}

function formatDate(iso?: string) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return iso; }
}
function statusColor(s: string) {
  if (s === "ok") return colors.success;
  if (s === "attention") return colors.warning;
  if (s === "maintenance") return colors.warning;
  return colors.error;
}
function equipIcon(cat: string): keyof typeof Ionicons.glyphMap {
  const map: Record<string, keyof typeof Ionicons.glyphMap> = {
    water_heater: "water",
    boiler: "flame",
    heat_pump: "snow",
    panel: "flash",
    ac: "snow",
    vmc: "sync",
    roof: "home",
    windows: "square-outline",
    doors: "log-in",
    smoke_detector: "warning",
    solar: "sunny",
    ev_charger: "battery-charging",
    water_softener: "water",
  };
  return map[cat] || "cog";
}

const styles = StyleSheet.create({
  hero: { height: 320, position: "relative", justifyContent: "space-between" },
  heroTop: { flexDirection: "row", paddingHorizontal: spacing.md, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(11,11,15,0.55)",
    borderWidth: 1, borderColor: "rgba(255,255,255,0.12)",
    alignItems: "center", justifyContent: "center",
  },
  heroBottom: { padding: spacing.lg, paddingBottom: spacing.xl },
  typeChip: {
    alignSelf: "flex-start",
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: "rgba(11,11,15,0.65)",
    borderWidth: 1, borderColor: colors.brand + "55",
  },
  metaChip: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: "rgba(11,11,15,0.55)",
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.12)",
  },
  quickWrap: {
    flexDirection: "row",
    marginTop: -spacing.lg,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  quickCard: { flex: 1, alignItems: "center", paddingVertical: spacing.sm },
  quickIcon: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: colors.brand + "18",
    borderWidth: 1, borderColor: colors.brand + "44",
    alignItems: "center", justifyContent: "center",
  },
  insightsCard: {
    marginTop: spacing.xl,
    marginHorizontal: spacing.lg,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  healthBar: {
    height: 8,
    backgroundColor: colors.surfaceTertiary,
    borderRadius: 4,
    overflow: "hidden",
  },
  healthFill: {
    height: "100%",
    backgroundColor: colors.brand,
    borderRadius: 4,
  },
  sectionHeader: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.lg,
    marginTop: spacing.xl, marginBottom: spacing.md,
  },
  emptyMini: {
    flexDirection: "row", alignItems: "center",
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  reminderRow: {
    flexDirection: "row", alignItems: "center",
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  reminderDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand, marginRight: spacing.md },
  statusPill: {
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radius.pill,
  },
  statusPillUp: { backgroundColor: colors.brand + "18", borderWidth: 1, borderColor: colors.brand + "44" },
  statusPillDue: { backgroundColor: colors.warning + "22", borderWidth: 1, borderColor: colors.warning + "55" },
  emptyEquip: {
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    flexDirection: "row", alignItems: "center",
  },
  emptyEquipIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brand + "18",
    alignItems: "center", justifyContent: "center",
    marginRight: spacing.md,
  },
  addChip: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "14",
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  equipCard: {
    width: 160,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    position: "relative",
  },
  equipIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: colors.brand + "18",
    alignItems: "center", justifyContent: "center",
  },
  statusDot: {
    position: "absolute", top: 12, right: 12,
    width: 8, height: 8, borderRadius: 4,
  },
  aiCard: {
    width: 240,
    padding: spacing.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.brand + "22",
    position: "relative",
  },
  aiIcon: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.brand + "18",
    alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.brand + "44",
  },
  soonPill: {
    position: "absolute", top: spacing.md, right: spacing.md,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.brand + "18",
    borderWidth: 1, borderColor: colors.brand + "55",
  },
  notesCard: {
    padding: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
});

const shareStyles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingTop: 10, paddingBottom: 40,
    borderTopWidth: 1, borderColor: colors.border,
  },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: "center", marginBottom: 14 },
  icon: {
    width: 44, height: 44, borderRadius: 12,
    backgroundColor: colors.brand + "1F",
    borderWidth: 1, borderColor: colors.brand + "55",
    alignItems: "center", justifyContent: "center",
  },
  close: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  linkBox: {
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  infoRow: { flexDirection: "row", alignItems: "flex-start", marginTop: spacing.md },
  actionBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    paddingVertical: 14, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  actionBtnPrimary: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    paddingVertical: 14, borderRadius: radius.md,
    backgroundColor: colors.brand,
  },
  revokeBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center",
    marginTop: spacing.md,
    paddingVertical: 10, borderRadius: radius.pill,
    backgroundColor: colors.error + "10",
    borderWidth: 1, borderColor: colors.error + "40",
    alignSelf: "center", paddingHorizontal: spacing.lg,
  },
});
