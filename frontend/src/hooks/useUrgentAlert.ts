/**
 * useUrgentAlert — hook FAQTOTUM V1.
 *
 * Polle `/bookings/received` toutes les N secondes et déclenche une
 * alerte (haptique + visuelle) dès qu'une NOUVELLE demande marquée
 * `urgent: true` apparaît côté artisan.
 *
 * Retourne l'ID de la dernière demande urgente (utile pour afficher un
 * toast overlay) + une fonction ``dismiss()`` pour l'acquitter.
 *
 * Notes preview / build natif :
 *   - Haptique : fonctionne en Expo Go sur device réel, no-op sur web.
 *   - Son OS : nécessite `expo-audio` avec un asset bundlé ; pour V1
 *     preview on se limite à haptique + banner visuel. Le son lock-screen
 *     n'arrivera qu'avec les push notifications (Sprint 1 Brique 3).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import * as Haptics from "expo-haptics";
import { api } from "@/src/api";

type ReceivedBooking = {
  booking_id: string;
  status: string;
  urgent?: boolean;
};

type Options = {
  intervalMs?: number;   // default 8000
  enabled?: boolean;     // default true
};

export type UrgentAlert = {
  bookingId: string;
  triggeredAt: number;
};

/**
 * Retourne :
 *   - alert   : le dernier événement urgent non acquitté (ou null)
 *   - dismiss : pour acquitter l'alerte affichée
 */
export function useUrgentAlert(opts: Options = {}) {
  const { intervalMs = 8000, enabled = true } = opts;
  const [alert, setAlert] = useState<UrgentAlert | null>(null);
  const knownIdsRef = useRef<Set<string>>(new Set());
  const firstLoadRef = useRef(true);

  const check = useCallback(async () => {
    try {
      const list = await api<ReceivedBooking[]>("/bookings/received");
      if (!Array.isArray(list)) return;
      const urgentPending = list.filter(
        (b) => b.urgent === true && b.status === "pending",
      );
      const currentIds = new Set(urgentPending.map((b) => b.booking_id));

      // Premier chargement : on hydrate la mémoire sans notifier.
      if (firstLoadRef.current) {
        knownIdsRef.current = currentIds;
        firstLoadRef.current = false;
        return;
      }

      // Détecte les NOUVEAUX IDs urgents.
      const fresh = urgentPending.filter(
        (b) => !knownIdsRef.current.has(b.booking_id),
      );
      knownIdsRef.current = currentIds;

      if (fresh.length > 0) {
        // Haptique heavy — 3 pulses successifs.
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(
          () => {},
        );
        setTimeout(
          () =>
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(
              () => {},
            ),
          200,
        );
        setTimeout(
          () =>
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy).catch(
              () => {},
            ),
          450,
        );
        setAlert({
          bookingId: fresh[0].booking_id,
          triggeredAt: Date.now(),
        });
      }
    } catch {
      /* silent — never break the UI for an alert poll */
    }
  }, []);

  const dismiss = useCallback(() => setAlert(null), []);

  useEffect(() => {
    if (!enabled) return;
    // Kick immediately then loop.
    check();
    const id = setInterval(check, intervalMs);
    return () => clearInterval(id);
  }, [enabled, intervalMs, check]);

  return { alert, dismiss };
}
