# Sprint 14 — Phase 1 — Bloc 3/8 · Artisans — ✅ MIGRÉ

## 1. Endpoints migrés (22)
| Méthode | Route | Auth requise |
|---|---|---|
| GET    | `/api/artisans` (filtrable) | public |
| GET    | `/api/artisans/top` | public |
| GET    | `/api/artisans/me` | auth |
| POST   | `/api/artisans/me` (upsert whitelist strict) | artisan |
| POST   | `/api/artisans/me/subscribe` | artisan |
| GET    | `/api/artisans/{artisan_id}` | public (404 si non-approuvé) |
| GET    | `/api/artisans/{artisan_id}/availability` | public |
| POST   | `/api/artisans/me/calendar/connect` | profil requis |
| POST   | `/api/artisans/me/position` | artisan |
| POST   | `/api/artisans/me/available-now` | artisan |
| POST   | `/api/artisans/me/slots` | artisan |
| GET    | `/api/artisans/me/slots` | artisan |
| DELETE | `/api/artisans/me/slots/{slot_id}` | artisan + ownership |
| GET    | `/api/artisans/{artisan_id}/slots` | public |
| GET    | `/api/artisans/{aid}/gallery` | public |
| POST   | `/api/artisans/me/gallery` | artisan |
| PATCH  | `/api/artisans/me/gallery/{project_id}` | artisan + ownership |
| DELETE | `/api/artisans/me/gallery/{project_id}` | artisan + ownership |
| GET    | `/api/artisans/me/scoreboard` | auth (404 sans profil) |
| GET    | `/api/artisans/me/finance` | artisan (`simulated:true`) |
| GET    | `/api/artisans/me/earnings` | artisan (`simulated:true`) |
| GET    | `/api/artisans/{aid}/level` | public |

**Endpoints NON migrés (hors périmètre Bloc 3)** :
- `/artisans/nearby` (lié au dispatch — Bloc 5)
- `/artisans/{id}/trust`, `/badges`, `/confidence-card`, `/recompute-trust` (trust engine — Bloc dédié)
- `/reviews/artisan/{id}` (module reviews)

## 2. Fichiers créés ou modifiés
| Fichier | Type | Notes |
|---|---|---|
| `/app/backend/routes/artisans.py` | ✨ créé | ~460 LOC — whitelist, validators stricts, ownership guards |
| `/app/backend/tests/test_sprint14_p1_bloc3_artisans.py` | ✨ créé | 26 tests dont ownership A/B, escalade rôle, validation zones/horaires |
| `/app/backend/server.py` | ✎ modifié | Import + mount router, 12 blocs legacy supprimés |
| `/app/backend/server.py.backup_p1_bloc3` | 💾 backup | Point de restauration avant migration |

## 3. Lignes retirées de `server.py`
- Avant Bloc 3 : `4331` lignes
- Après Bloc 3 : `3905` lignes
- **Retirées ce bloc : `426` lignes**
- Cumul Phase 1 (Bloc 1 + 2 + 3) : **−875 lignes** (départ 4767 → 3905)

## 4. Résultats exacts des tests — 3 runs consécutifs (vérifiés par testing_agent iteration_19)

### Nouveaux tests Bloc 3
| Test | Résultat |
|---|---|
| `test_sprint14_p1_bloc3_artisans.py` (26 tests) | **26/26 ✅** en 1.96s |

### Suite complète (déterministe — 3 runs identiques)
| Run | Passed | Failed | Cause |
|---|---|---|---|
| 1 | **462/463** | 1 | `test_create_org_valid_and_persists` (pré-existant, sans rapport avec les artisans) |
| 2 | **462/463** | 1 | idem |
| 3 | **462/463** | 1 | idem |

- ✅ **Zéro régression** sur les 383+ tests d'origine
- ✅ Aucune nouvelle flakiness introduite
- ⚠️ 1 échec pré-existant (`test_enterprise_sprint::test_create_org_valid_and_persists`) — reproduit sur `backup_p1_bloc2` avant Bloc 3 → **hors sujet**

## 5. Permissions ajoutées

### Whitelist stricte sur POST /artisans/me
```python
EDITABLE_ARTISAN_FIELDS = {
    "trade", "title", "bio", "city", "hourly_rate", "photo", "phone",
    "available", "years_experience", "emergency_capable", "website",
    "intervention_zones", "working_hours",
}
```
Tous les autres champs envoyés par l'utilisateur (incluant `role`, `verification_status`, `trust_score`, `rating`, `reviews_count`, `jobs_done`, `is_subscribed`, `stripe_account_id`, `admin_notes`, `identity_verified`, `insurance_verified`, `background_checked`) sont **silencieusement ignorés**. Vérifié par testing_agent en manuel.

### Ownership guards
- **Slots** : filtre Mongo composite `{"slot_id": ..., "artisan_id": my_artisan_id}` → 404 uniforme
- **Gallery** : filtre composite `{"project_id": ..., "artisan_id": my_artisan_id}` → 404 uniforme
- **Aucun 403 sur les cross-artisans** (anti-enumeration)

### Validators Pydantic stricts
- `trade` : slug regex `^[a-z0-9_\-]+$` → 422 sinon
- `phone` : caractères `digits + -()`, sinon 422
- `hourly_rate` : `ge=0 le=1000` → 422 hors bornes
- `bio` : `max_length=1500`, refus `<script`
- `WorkingHoursSlot` : `end > start`, format `HH:MM` regex
- `InterventionZone` : ville regex, `radius_km 0..500`
- `website` : `HttpUrl` Pydantic
- `photo` : `max_length=2_000_000` (2 Mo base64)

### Audit logs
- `artisan.profile_created`
- `artisan.profile_updated`
- `artisan.subscribed` (avec `simulated: true`)
- `artisan.calendar_connected` (avec `simulated: true`)

### Vérification pro — architecture posée sans workflow complet
- Champ `verification_status ∈ {pending, identity_verified, business_verified, insurance_verified, approved, rejected}`
- Nouveaux profils démarrent en `pending`
- **Public listings filtrent** : `verification_status ∈ {approved, null}` (null = legacy compat pour anciens seeds)
- `GET /artisans/{id}` retourne **404** si non-approuvé (pas d'énumération)
- Le workflow complet (endpoints admin d'approbation) est à faire dans un bloc dédié plus tard

### Trust score honnête
- Nouveau profil : `trust_score=0`, `rating=0`, `reviews_count=0`, `jobs_done=0`
- `trust_engine.persist()` **N'EST PLUS APPELÉ** au CREATE (le score restait alors à 0 → correct)
- Il n'est appelé qu'au UPDATE, et **seulement si** `jobs_done > 0 OR reviews_count > 0`
- Anciens seeds gardent leurs valeurs (backward compat) — aucune migration destructive

## 6. Données artisan encore simulées

Les champs suivants restent marqués `simulated: true` dans les réponses jusqu'à intégration réelle :

| Feature | Endpoint | Champ marqueur |
|---|---|---|
| Position GPS live | `POST /artisans/me/position` | (mis à jour manuellement par le pro) |
| Disponibilité "now" | `POST /artisans/me/available-now` | (toggle manuel) |
| Calendrier externe | `POST /artisans/me/calendar/connect` | `simulated: true` |
| Abonnement | `POST /artisans/me/subscribe` | `simulated: true` (Stripe subscription mockée) |
| Finance dashboard | `GET /artisans/me/finance` | `simulated: true` |
| Earnings summary | `GET /artisans/me/earnings` | `simulated: true` |
| Nouveau profil | tous | `simulated: true` (jusqu'à première activité réelle) |

Anciens seeds conservent leurs valeurs et **n'ont PAS le flag `simulated`** — c'est intentionnel pour la démo actuelle.

## 7. Dette technique restante

1. **Doublon `get_current_user`** dans `server.py:74-102` (legacy) vs `security/dependencies.py`. Non-critique tant que les 2 lisent `user_sessions`. À supprimer en fin de Phase 1 (Bloc 9).
2. **`_require_pro` inutilisé** dans `server.py` — la fonction est toujours définie mais plus référencée. À supprimer.
3. **`enrich_artisan` gardé dans `server.py`** — utilisé par les blocs non migrés (bookings, missions, disputes, matching). Sortira en `services/artisans.py` au Bloc 5.
4. **`ArtisanProfileInput`, `CalendarConnectInput`, `PositionInput`, `SlotInput`, `GalleryProjectInput`, `PortfolioPatchInput`** encore dans `server.py` bien que le code qui les référençait ait été déplacé. Les supprimer déclenche pyright/lint warning mais pas de crash runtime. À nettoyer au Bloc 9.
5. **3 backups .py sur disque** (`backup_p1`, `backup_p1_bloc2`, `backup_p1_bloc3`) — à supprimer en fin de Phase 1.
6. **Test `test_create_org_valid_and_persists`** pré-existant en échec — hors sujet mais à traiter dans un ticket séparé.
7. **Import bcrypt encore dupliqué** dans `server.py`, `routes/auth.py`, `routes/security.py` — sortir dans `services/auth_utils.py` recommandé au Bloc 4.

## 8. Risques identifiés & mitigés

| Risque | Sévérité | Mitigation appliquée |
|---|---|---|
| Escalade rôle via POST /artisans/me | 🔴 Critique | Whitelist stricte + test dédié |
| Client modifie profil artisan | 🔴 Critique | `_require_artisan` guard (403) |
| Trust Score artificiel | 🟠 Haute | Créations démarrent à 0, engine désactivé au CREATE |
| Note parfaite sans activité | 🟠 Haute | `rating=0.0` au CREATE (avant : 5.0) |
| Artisan invisible avant approbation | 🟠 Haute | Filtre `verification_status` sur toutes les lectures publiques + 404 sur GET par id |
| Enumeration slots/gallery | 🟠 Haute | Filtre Mongo composite + 404 uniforme |
| XSS sur bio/title/nom ville | 🟡 Moyenne | Validators Pydantic + regex + rejet `<script` |
| Photo > 2 Mo | 🟡 Moyenne | `max_length=2_000_000` sur `photo` |
| URL malformée website | 🟡 Moyenne | Pydantic `HttpUrl` |
| Contrat API cassé | 🟠 Haute | Legacy contracts préservés (400/404 vs 422/403) — vérifié testing_agent |
| Payments simulés confondus avec réels | 🔴 Critique | `simulated: true` sur finance/earnings/subscribe/calendar |
| Backup files sur disque | 🟢 Faible | Point de restauration explicite, à supprimer en fin de Phase 1 |

## Point de restauration

```bash
# Rollback Bloc 3 uniquement
cp /app/backend/server.py.backup_p1_bloc3 /app/backend/server.py
rm /app/backend/routes/artisans.py
rm /app/backend/tests/test_sprint14_p1_bloc3_artisans.py
sudo supervisorctl restart backend
```

---

**Statut Phase 1**
- ✅ Bloc 1 (auth + security) — 24 endpoints
- ✅ Bloc 2 (users + roles) — 7 endpoints
- ✅ Bloc 3 (artisans) — 22 endpoints
- ⏸️ Bloc 4 (missions + bookings + interventions) — en attente
- ⏸️ Blocs 5-8 — en attente

**Total migré : 53 endpoints · −875 lignes de `server.py`**
