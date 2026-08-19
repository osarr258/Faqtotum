/**
 * Artisan Profile — FAQTOTUM v1
 *
 * Structure éditoriale claire :
 *   1. Header (photo + prénom + métier + statut vérifié)
 *   2. Stats (Note · Missions · Réponse) — readonly
 *   3. Profil public (éditable)   → visible par les clients
 *   4. Coordonnées privées         → jamais public
 *   5. Vérification                → statut readonly
 *   6. Abonnement                  → CTA vers /(artisan)/subscription
 *   7. Compte                      → Sécurité + Logout
 *
 * Aucun endpoint backend modifié. Utilise les champs existants du
 * whitelist EDITABLE_ARTISAN_FIELDS (trade, title, bio, city, phone,
 * hourly_rate, photo, years_experience).
 */
import { useEffect, useState } from "react";
import {
  View,
  StyleSheet,
  ScrollView,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Avatar, Button } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import {
  colors,
  font,
  fontSize,
  radius,
  spacing,
} from "@/src/theme";

type Category = { slug: string; name: string };

type Profile = {
  trade?: string;
  title?: string;
  bio?: string;
  city?: string;
  hourly_rate?: number;
  phone?: string;
  photo?: string | null;
  years_experience?: number;
  rating?: number;
  reviews_count?: number;
  response_min?: number;
  jobs_done?: number;
  verification_status?: string;
  is_subscribed?: boolean;
};

const VERIF_LABEL: Record<string, string> = {
  pending: "En attente",
  identity_verified: "Identité vérifiée",
  business_verified: "SIRET vérifié",
  insurance_verified: "Assurance vérifiée",
  approved: "Vérifié",
  rejected: "Refusé",
};

export default function ArtisanProfileScreen() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [categories, setCategories] = useState<Category[]>([]);
  const [profile, setProfile] = useState<Profile>({});
  const [trade, setTrade] = useState("");
  const [title, setTitle] = useState("");
  const [bio, setBio] = useState("");
  const [city, setCity] = useState("");
  const [rate, setRate] = useState("");
  const [phone, setPhone] = useState("");
  const [years, setYears] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Category[]>("/categories", { auth: false })
      .then(setCategories)
      .catch(() => {});
    api<Profile | null>("/artisans/me")
      .then((p) => {
        if (p) {
          setProfile(p);
          setTrade(p.trade || "");
          setTitle(p.title || "");
          setBio(p.bio || "");
          setCity(p.city || "");
          setRate(p.hourly_rate ? String(p.hourly_rate) : "");
          setPhone(p.phone || "");
          setYears(
            p.years_experience != null ? String(p.years_experience) : "",
          );
        }
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    setError("");
    setMsg("");
    if (!trade || !title) {
      setError("Choisissez un métier et un titre professionnel.");
      return;
    }
    setSaving(true);
    try {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
      const updated = await api<Profile>("/artisans/me", {
        method: "POST",
        body: {
          trade,
          title,
          bio,
          city,
          hourly_rate: parseFloat(rate) || 0,
          phone,
          years_experience: years ? parseInt(years, 10) : undefined,
        },
      });
      setProfile((p) => ({ ...p, ...updated }));
      setMsg("Modifications enregistrées.");
      Haptics.notificationAsync(
        Haptics.NotificationFeedbackType.Success,
      ).catch(() => {});
    } catch (e) {
      const s = e instanceof Error ? e.message : "Erreur";
      setError(s);
    } finally {
      setSaving(false);
    }
  };

  const doLogout = async () => {
    Alert.alert(
      "Déconnexion",
      "Vous êtes sur le point de vous déconnecter.",
      [
        { text: "Annuler", style: "cancel" },
        {
          text: "Se déconnecter",
          style: "destructive",
          onPress: async () => {
            await logout();
            router.replace("/welcome");
          },
        },
      ],
    );
  };

  const firstName = (user?.name || "").split(" ")[0] || "";
  const tradeLabel =
    categories.find((c) => c.slug === trade)?.name ||
    (profile.trade ? profile.trade : "Non défini");
  const verified = profile.verification_status === "approved";
  const verifLabel =
    VERIF_LABEL[profile.verification_status || "pending"] || "En attente";

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={{
          paddingTop: insets.top + spacing.md,
          paddingBottom: insets.bottom + spacing["3xl"],
        }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* --- Header block ---------------------------------------- */}
        <View style={styles.headerBlock}>
          <View style={styles.avatarWrap}>
            <Avatar name={user?.name} uri={profile.photo || null} size={88} />
            {verified && (
              <View style={styles.verifiedDot}>
                <Ionicons
                  name="checkmark"
                  size={14}
                  color={colors.textInverse}
                />
              </View>
            )}
          </View>
          <Txt weight="extrabold" size="2xl" style={{ marginTop: spacing.md }}>
            {firstName || "Artisan"}
          </Txt>
          <View style={styles.tradeBadge}>
            <Ionicons name="briefcase" size={12} color={colors.onSurface} />
            <Txt weight="bold" size="sm" style={{ marginLeft: 6 }}>
              {tradeLabel}
            </Txt>
          </View>
          <View style={styles.verifPill}>
            <View
              style={[
                styles.verifDot,
                { backgroundColor: verified ? colors.success : colors.warning },
              ]}
            />
            <Txt size="sm" color={colors.muted}>
              {verifLabel}
            </Txt>
          </View>
        </View>

        {/* --- Stats ----------------------------------------------- */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Ionicons name="star" size={14} color={colors.brand} />
            <Txt weight="extrabold" size="xl" style={{ marginTop: 4 }}>
              {profile.rating != null ? profile.rating.toFixed(1) : "—"}
            </Txt>
            <Txt size="sm" color={colors.muted}>
              {(profile.reviews_count || 0) + " avis"}
            </Txt>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="briefcase" size={14} color={colors.brand} />
            <Txt weight="extrabold" size="xl" style={{ marginTop: 4 }}>
              {profile.jobs_done || 0}
            </Txt>
            <Txt size="sm" color={colors.muted}>
              Missions
            </Txt>
          </View>
          <View style={styles.statBox}>
            <Ionicons name="time-outline" size={14} color={colors.brand} />
            <Txt weight="extrabold" size="xl" style={{ marginTop: 4 }}>
              {profile.response_min ? `${profile.response_min}m` : "—"}
            </Txt>
            <Txt size="sm" color={colors.muted}>
              Réponse
            </Txt>
          </View>
        </View>

        {/* --- Public profile edit --------------------------------- */}
        <Section title="Profil public" subtitle="Visible par les clients">
          <Label text="Métier" />
          <View style={styles.chips}>
            {categories.map((c) => {
              const active = c.slug === trade;
              return (
                <Pressable
                  key={c.slug}
                  testID={`trade-${c.slug}`}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setTrade(c.slug);
                  }}
                  style={[styles.chip, active && styles.chipActive]}
                >
                  <Txt
                    weight="bold"
                    size="sm"
                    color={active ? colors.textInverse : colors.onSurface}
                  >
                    {c.name}
                  </Txt>
                </Pressable>
              );
            })}
          </View>

          <Label text="Titre professionnel" />
          <TextInput
            testID="title-input"
            value={title}
            onChangeText={setTitle}
            placeholder="Plombier chauffagiste certifié"
            placeholderTextColor={colors.muted}
            style={styles.input}
          />

          <Label text="Description" />
          <TextInput
            testID="bio-input"
            value={bio}
            onChangeText={setBio}
            placeholder="Décrivez votre expérience, vos services, ce qui vous distingue…"
            placeholderTextColor={colors.muted}
            multiline
            style={[
              styles.input,
              { minHeight: 108, textAlignVertical: "top", paddingTop: 12 },
            ]}
          />

          <View style={styles.row2}>
            <View style={{ flex: 1 }}>
              <Label text="Ville" />
              <TextInput
                testID="city-input"
                value={city}
                onChangeText={setCity}
                placeholder="Paris 11e"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Label text="Expérience (années)" />
              <TextInput
                testID="years-input"
                value={years}
                onChangeText={setYears}
                placeholder="8"
                placeholderTextColor={colors.muted}
                keyboardType="numeric"
                style={styles.input}
              />
            </View>
          </View>

          <Label text="Tarif horaire (€)" />
          <TextInput
            testID="rate-input"
            value={rate}
            onChangeText={setRate}
            placeholder="55"
            placeholderTextColor={colors.muted}
            keyboardType="numeric"
            style={styles.input}
          />
        </Section>

        {/* --- Private contact ------------------------------------- */}
        <Section
          title="Coordonnées privées"
          subtitle="Jamais visible par les clients"
          icon="lock-closed"
        >
          <Label text="Téléphone" />
          <TextInput
            testID="phone-input"
            value={phone}
            onChangeText={setPhone}
            placeholder="+33 6 12 34 56 78"
            placeholderTextColor={colors.muted}
            keyboardType="phone-pad"
            style={styles.input}
          />
        </Section>

        {/* --- Save button ---------------------------------------- */}
        <View style={{ paddingHorizontal: spacing.lg, marginTop: spacing.lg }}>
          {error ? (
            <Txt color={colors.error} size="sm" style={{ marginBottom: 8 }}>
              {error}
            </Txt>
          ) : null}
          {msg ? (
            <Txt color={colors.success} size="sm" style={{ marginBottom: 8 }}>
              {msg}
            </Txt>
          ) : null}
          <Button
            testID="save-profile-button"
            title="Enregistrer les modifications"
            loading={saving}
            onPress={save}
          />
        </View>

        {/* --- Verification --------------------------------------- */}
        <Section title="Vérification" subtitle="Statut du dossier">
          <View style={styles.verifCard}>
            <View
              style={[
                styles.verifIcon,
                { backgroundColor: verified ? colors.success : colors.surfaceSecondary },
              ]}
            >
              <Ionicons
                name={verified ? "shield-checkmark" : "shield-outline"}
                size={22}
                color={verified ? colors.textInverse : colors.brand}
              />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold">{verifLabel}</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                {verified
                  ? "Votre profil est vérifié et mis en avant."
                  : "La gestion des documents arrive prochainement."}
              </Txt>
            </View>
          </View>
        </Section>

        {/* --- Subscription CTA ------------------------------------ */}
        <Section title="Abonnement">
          <Pressable
            testID="go-subscription"
            onPress={() => router.push("/(artisan)/subscription")}
            style={({ pressed }) => [
              styles.navCard,
              pressed && { opacity: 0.9 },
            ]}
          >
            <View style={styles.navIcon}>
              <Ionicons name="diamond-outline" size={22} color={colors.brand} />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold">
                {profile.is_subscribed ? "Abonnement actif" : "Passer Premium"}
              </Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                {profile.is_subscribed
                  ? "Vous êtes référencé auprès des clients."
                  : "Recevez plus de demandes qualifiées."}
              </Txt>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>
        </Section>

        {/* --- Account -------------------------------------------- */}
        <Section title="Compte">
          <Pressable
            testID="go-security"
            onPress={() => router.push("/security")}
            style={({ pressed }) => [
              styles.navCard,
              pressed && { opacity: 0.9 },
            ]}
          >
            <View style={styles.navIcon}>
              <Ionicons name="shield-outline" size={22} color={colors.brand} />
            </View>
            <View style={{ flex: 1, marginLeft: spacing.md }}>
              <Txt weight="bold">Sécurité & confidentialité</Txt>
              <Txt size="sm" color={colors.muted} style={{ marginTop: 2 }}>
                Mot de passe, sessions, exports RGPD
              </Txt>
            </View>
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>

          <Pressable
            testID="logout-button"
            onPress={doLogout}
            style={({ pressed }) => [
              styles.logoutBtn,
              pressed && { opacity: 0.85 },
            ]}
          >
            <Ionicons name="log-out-outline" size={18} color={colors.error} />
            <Txt weight="bold" color={colors.error} style={{ marginLeft: 8 }}>
              Se déconnecter
            </Txt>
          </Pressable>
        </Section>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Section({
  title,
  subtitle,
  icon,
  children,
}: {
  title: string;
  subtitle?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHead}>
        {icon ? (
          <Ionicons
            name={icon}
            size={14}
            color={colors.muted}
            style={{ marginRight: 6 }}
          />
        ) : null}
        <Txt weight="bold" size="lg">
          {title}
        </Txt>
        {subtitle ? (
          <Txt size="sm" color={colors.muted} style={{ marginLeft: 8 }}>
            · {subtitle}
          </Txt>
        ) : null}
      </View>
      {children}
    </View>
  );
}

function Label({ text }: { text: string }) {
  return (
    <Txt
      weight="bold"
      size="sm"
      color={colors.muted}
      style={{ marginBottom: 6, marginTop: spacing.md }}
    >
      {text}
    </Txt>
  );
}

const styles = StyleSheet.create({
  headerBlock: {
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.lg,
  },
  avatarWrap: {
    position: "relative",
  },
  verifiedDot: {
    position: "absolute",
    right: -2,
    bottom: -2,
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.brand,
    borderWidth: 3,
    borderColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  tradeBadge: {
    marginTop: 6,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
  },
  verifPill: {
    marginTop: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  verifDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statsRow: {
    flexDirection: "row",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.xl,
  },
  statBox: {
    flex: 1,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "flex-start",
    backgroundColor: colors.surface,
  },
  section: {
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.xl,
  },
  sectionHead: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
    flexWrap: "wrap",
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  chip: {
    height: 36,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceSecondary,
  },
  chipActive: {
    backgroundColor: colors.brand,
  },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    height: 52,
    fontFamily: font.medium,
    fontSize: fontSize.base,
    color: colors.onSurface,
  },
  row2: {
    flexDirection: "row",
    gap: spacing.md,
  },
  verifCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  verifIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  navCard: {
    flexDirection: "row",
    alignItems: "center",
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
  },
  navIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  logoutBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.md,
    height: 52,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
  },
});
