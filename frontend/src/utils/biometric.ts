/**
 * Biometric authentication helper (Face ID / Touch ID / Android biometrics).
 * Non-web only — safely no-ops on web/Expo Go without support.
 */
import { Platform } from "react-native";
import * as LocalAuthentication from "expo-local-authentication";
import { storage } from "@/src/utils/storage";

const KEY_ENABLED = "pc_biometric_enabled";
const KEY_ASKED = "pc_biometric_asked";

export type BiometricSupport = {
  supported: boolean;
  enrolled: boolean;
  type: "face" | "fingerprint" | "iris" | "none";
  label: string;
};

/** Introspect device capability. */
export async function getBiometricSupport(): Promise<BiometricSupport> {
  if (Platform.OS === "web") {
    return { supported: false, enrolled: false, type: "none", label: "Biométrie" };
  }
  try {
    const hasHw = await LocalAuthentication.hasHardwareAsync();
    const enrolled = await LocalAuthentication.isEnrolledAsync();
    const types = await LocalAuthentication.supportedAuthenticationTypesAsync();

    let type: BiometricSupport["type"] = "none";
    let label = "Biométrie";

    if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) {
      type = "face";
      label = Platform.OS === "ios" ? "Face ID" : "Reconnaissance faciale";
    } else if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) {
      type = "fingerprint";
      label = Platform.OS === "ios" ? "Touch ID" : "Empreinte digitale";
    } else if (types.includes(LocalAuthentication.AuthenticationType.IRIS)) {
      type = "iris";
      label = "Iris";
    }

    return { supported: hasHw, enrolled, type, label };
  } catch {
    return { supported: false, enrolled: false, type: "none", label: "Biométrie" };
  }
}

/** Whether the user has enabled biometric unlock. */
export async function isBiometricEnabled(): Promise<boolean> {
  const v = await storage.secureGet<boolean>(KEY_ENABLED, false);
  return !!v;
}

/** Whether the user was already asked to enable biometric (avoid re-asking). */
export async function wasBiometricAsked(): Promise<boolean> {
  const v = await storage.getItem<boolean>(KEY_ASKED, false);
  return !!v;
}

export async function markBiometricAsked(): Promise<void> {
  await storage.setItem(KEY_ASKED, true);
}

export async function setBiometricEnabled(enabled: boolean): Promise<void> {
  await storage.secureSet(KEY_ENABLED, enabled);
}

/** Trigger the native prompt. Returns true if authenticated. */
export async function authenticateWithBiometric(promptMessage?: string): Promise<boolean> {
  if (Platform.OS === "web") return false;
  try {
    const res = await LocalAuthentication.authenticateAsync({
      promptMessage: promptMessage || "Déverrouillez Auxora",
      cancelLabel: "Annuler",
      fallbackLabel: "Utiliser le mot de passe",
      disableDeviceFallback: false,
    });
    return res.success === true;
  } catch {
    return false;
  }
}
