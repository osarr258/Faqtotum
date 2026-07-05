import { useEffect, useState } from "react";
import { View, StyleSheet, ScrollView, TextInput, Pressable, KeyboardAvoidingView, Platform } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { api } from "@/src/api";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

type Category = { slug: string; name: string };

export default function ArtisanProfile() {
  const { logout } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [categories, setCategories] = useState<Category[]>([]);
  const [trade, setTrade] = useState("");
  const [title, setTitle] = useState("");
  const [bio, setBio] = useState("");
  const [city, setCity] = useState("");
  const [rate, setRate] = useState("");
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Category[]>("/categories", { auth: false }).then(setCategories).catch(() => {});
    api<any>("/artisans/me").then((p) => {
      if (p) {
        setTrade(p.trade || ""); setTitle(p.title || ""); setBio(p.bio || "");
        setCity(p.city || ""); setRate(p.hourly_rate ? String(p.hourly_rate) : ""); setPhone(p.phone || "");
      }
    }).catch(() => {});
  }, []);

  const save = async () => {
    setError(""); setMsg("");
    if (!trade || !title) { setError("Choisissez un métier et un titre."); return; }
    setSaving(true);
    try {
      await api("/artisans/me", { method: "POST", body: { trade, title, bio, city, hourly_rate: parseFloat(rate) || 0, phone } });
      setMsg("Profil enregistré avec succès ✓");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const doLogout = async () => { await logout(); router.replace("/onboarding"); };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surface }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing["3xl"] }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <Txt weight="extrabold" size="2xl" style={{ marginBottom: spacing.xs }}>Mon profil pro</Txt>
        <Txt color={colors.muted} style={{ marginBottom: spacing.xl }}>Ces informations sont visibles par les clients.</Txt>

        <Label text="Métier" />
        <View style={styles.chips}>
          {categories.map((c) => {
            const active = c.slug === trade;
            return (
              <Pressable key={c.slug} testID={`trade-${c.slug}`} onPress={() => setTrade(c.slug)} style={[styles.chip, { backgroundColor: active ? colors.brand : colors.surfaceSecondary }]}>
                <Txt weight="semibold" size="sm" color={active ? colors.onSurfaceInverse : colors.onSurface}>{c.name}</Txt>
              </Pressable>
            );
          })}
        </View>

        <Label text="Titre" />
        <TextInput testID="title-input" value={title} onChangeText={setTitle} placeholder="Ex: Plombier chauffagiste certifié" placeholderTextColor={colors.muted} style={styles.input} />

        <Label text="Ville" />
        <TextInput testID="city-input" value={city} onChangeText={setCity} placeholder="Ex: Paris 11e" placeholderTextColor={colors.muted} style={styles.input} />

        <Label text="Tarif horaire (€)" />
        <TextInput testID="rate-input" value={rate} onChangeText={setRate} placeholder="Ex: 55" keyboardType="numeric" placeholderTextColor={colors.muted} style={styles.input} />

        <Label text="Téléphone" />
        <TextInput testID="phone-input" value={phone} onChangeText={setPhone} placeholder="Ex: +33 6 12 34 56 78" keyboardType="phone-pad" placeholderTextColor={colors.muted} style={styles.input} />

        <Label text="Description" />
        <TextInput testID="bio-input" value={bio} onChangeText={setBio} placeholder="Présentez votre expérience et vos services…" multiline placeholderTextColor={colors.muted} style={[styles.input, { minHeight: 100, textAlignVertical: "top", paddingTop: spacing.md }]} />

        {error ? <Txt color={colors.error} size="sm" style={{ marginTop: spacing.md }}>{error}</Txt> : null}
        {msg ? <Txt color={colors.success} size="sm" style={{ marginTop: spacing.md }}>{msg}</Txt> : null}

        <Button testID="save-profile-button" title="Enregistrer" loading={saving} onPress={save} style={{ marginTop: spacing.xl }} />

        <Pressable testID="logout-button" onPress={doLogout} style={styles.logout}>
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Txt weight="bold" color={colors.error} style={{ marginLeft: spacing.sm }}>Se déconnecter</Txt>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Label({ text }: { text: string }) {
  return <Txt weight="semibold" size="sm" color={colors.onSurfaceSecondary} style={{ marginBottom: spacing.sm, marginTop: spacing.md }}>{text}</Txt>;
}

const styles = StyleSheet.create({
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { height: 38, paddingHorizontal: spacing.lg, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.lg, height: 52, fontFamily: font.medium, fontSize: fontSize.base, color: colors.onSurface },
  logout: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.lg, height: 54, borderRadius: radius.md, backgroundColor: "#FEE2E2" },
});
