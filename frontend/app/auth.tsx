import { useState } from "react";
import { View, StyleSheet, TextInput, ScrollView, KeyboardAvoidingView, Platform, Pressable } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Txt, Button } from "@/src/components/ui";
import { useAuth } from "@/src/context/AuthContext";
import { colors, font, fontSize, radius, spacing } from "@/src/theme";

export default function Auth() {
  const { role = "client" } = useLocalSearchParams<{ role: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { register, login, loginWithGoogle } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("register");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState("");

  const isArtisan = role === "artisan";

  const submit = async () => {
    setError("");
    if (!email || !password || (mode === "register" && !name)) {
      setError("Veuillez remplir tous les champs.");
      return;
    }
    setLoading(true);
    try {
      if (mode === "register") {
        await register(email.trim(), password, name.trim(), role as string);
      } else {
        await login(email.trim(), password);
      }
      router.replace("/");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const google = async () => {
    setError("");
    setGoogleLoading(true);
    try {
      await loginWithGoogle(role as string);
      router.replace("/");
    } catch (e: any) {
      setError(e.message || "Connexion Google échouée");
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surface }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <Pressable testID="back-button" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>

        <View style={[styles.roleTag, { backgroundColor: isArtisan ? "#D1FAE5" : colors.surfaceSecondary }]}>
          <Ionicons name={isArtisan ? "hammer" : "search"} size={14} color={isArtisan ? colors.success : colors.onSurface} />
          <Txt weight="semibold" size="sm" color={isArtisan ? colors.success : colors.onSurface} style={{ marginLeft: 6 }}>
            {isArtisan ? "Espace Pro" : "Espace Client"}
          </Txt>
        </View>

        <Txt weight="extrabold" size="3xl" style={{ marginTop: spacing.lg }}>
          {mode === "register" ? "Créer un compte" : "Bon retour"}
        </Txt>
        <Txt color={colors.muted} size="lg" style={{ marginTop: spacing.xs, marginBottom: spacing.xl }}>
          {mode === "register" ? "Rejoignez ProConnect en moins d'une minute." : "Connectez-vous pour continuer."}
        </Txt>

        {mode === "register" && (
          <Field testID="name-input" icon="person-outline" placeholder="Nom complet" value={name} onChangeText={setName} />
        )}
        <Field testID="email-input" icon="mail-outline" placeholder="Adresse email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
        <Field testID="password-input" icon="lock-closed-outline" placeholder="Mot de passe" value={password} onChangeText={setPassword} secureTextEntry />

        {error ? <Txt color={colors.error} size="sm" style={{ marginBottom: spacing.md }}>{error}</Txt> : null}

        <Button testID="submit-button" title={mode === "register" ? "Créer mon compte" : "Se connecter"} loading={loading} onPress={submit} />

        {mode === "register" && (
          <View style={styles.reassure}>
            <Ionicons name="checkmark-circle" size={13} color={colors.success} />
            <Txt size="sm" color={colors.muted} style={{ marginLeft: 6 }}>Inscription gratuite • Sécurisé • Moins de 2 minutes</Txt>
          </View>
        )}

        <View style={styles.divider}>
          <View style={styles.line} />
          <Txt color={colors.muted} size="sm" style={{ marginHorizontal: spacing.md }}>ou</Txt>
          <View style={styles.line} />
        </View>

        <Button testID="google-button" title="Continuer avec Google" variant="outline" icon="logo-google" loading={googleLoading} onPress={google} />

        <Pressable testID="toggle-mode" onPress={() => setMode(mode === "register" ? "login" : "register")} style={{ marginTop: spacing.xl, alignItems: "center" }}>
          <Txt color={colors.muted}>
            {mode === "register" ? "Déjà un compte ? " : "Pas encore de compte ? "}
            <Txt weight="bold" color={colors.onSurface}>{mode === "register" ? "Se connecter" : "S'inscrire"}</Txt>
          </Txt>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({ icon, testID, ...props }: any) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={[styles.field, focused && styles.fieldFocused]}>
      <Ionicons name={icon} size={20} color={focused ? colors.brand : colors.muted} />
      <TextInput
        testID={testID}
        placeholderTextColor={colors.muted}
        style={styles.input}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        {...props}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: spacing.lg },
  back: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  roleTag: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  field: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.lg, height: 58, marginBottom: spacing.md, gap: spacing.sm },
  fieldFocused: { borderColor: colors.brand, backgroundColor: colors.surfaceTertiary },
  reassure: { flexDirection: "row", alignItems: "center", justifyContent: "center", marginTop: spacing.md },
  input: { flex: 1, fontFamily: font.medium, fontSize: fontSize.lg, color: colors.onSurface },
  divider: { flexDirection: "row", alignItems: "center", marginVertical: spacing.lg },
  line: { flex: 1, height: 1, backgroundColor: colors.border },
});
