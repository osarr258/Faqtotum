import * as Haptics from "expo-haptics";

/** Unified haptic vocabulary. Silent-fail on web. */
export const hap = {
  tap:  () => Haptics.selectionAsync().catch(() => {}),
  soft: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}),
  firm: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}),
  hard: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(() => {}),
  ok:   () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}),
  warn: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {}),
  err:  () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {}),
};
