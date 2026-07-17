# Sprint 14 — Phase 1 — Bloc 4/8 · Missions + Bookings + Interventions — ✅ MIGRÉ

## 1. Correction du test préexistant

`test_create_org_valid_and_persists` — cause racine :
`GET /organizations/mine` limitait `to_list(50)` sans tri, donc quand un utilisateur avait >50 memberships (l'utilisateur `client.test@auxora.fr` en avait 68 après les runs précédents), la nouvelle org sortait du set retourné.

**Fix appliqué** dans `server.py` : `sort("created_at", -1)` push dans Mongo + `to_list(500)`.

**Résultat** : 463/463 sur 3 runs consécutifs avant même de démarrer le Bloc 4.

## 2. Endpoints migrés (17)

### Bookings — `routes/bookings.py`
- `POST /api/bookings` — création avec validation stricte (slot regex, XSS refus)
- `GET /api/bookings/mine` — sort Mongo, annotate_reviewed
- `GET /api/bookings/received` — sort Mongo
- `PATCH /api/bookings/{booking_id}` — state machine + compare-and-set atomique

### Missions — `routes/missions.py`
- `POST /api/missions` — création (searching/proposed)
- `POST /api/missions/{id}/book`
- `POST /api/missions/{id}/refuse`
- `POST /api/missions/{id}/confirm`
- `GET /api/missions/mine` — sort Mongo
- `GET /api/missions/{id}` — tracking simulé + auto-transition en_route→arrived
- `POST /api/missions/{id}/pro_accept` — **AUTH OBLIGATOIRE (Sprint 14 requirement)** + atomic compare-and-set

### Interventions — `routes/interventions.py`
- `POST /api/interventions/request`
- `GET /api/interventions/mine`
- `GET /api/interventions/{iv_id}`
- `POST /api/interventions/{iv_id}/accept` (artisan)
- `POST /api/interventions/{iv_id}/refuse` (artisan)
- `POST /api/interventions/{iv_id}/cancel` (client OR artisan selon état)

**Non-migré (payment scope, out of Bloc 4)** : `/interventions/{id}/start`, `/finish`, `/deposit/*`, `/final/*`, `/validate`, `/payment-summary`, `/missions/{id}/complete`.

## 3. Fichiers créés ou modifiés

| Fichier | Type | Notes |
|---|---|---|
| `services/status_transitions.py` | ✨ créé | State machine centralisée (BOOKING/MISSION/INTERVENTION_TRANSITIONS) |
| `routes/bookings.py` | ✨ créé | ~180 LOC |
| `routes/missions.py` | ✨ créé | ~340 LOC |
| `routes/interventions.py` | ✨ créé | ~180 LOC |
| `tests/test_sprint14_p1_bloc4_mission_flow.py` | ✨ créé | 22 tests |
| `server.py` | ✎ modifié | Fix org/mine + imports + mount routers + blocs supprimés + helpers restaurés |
| `tests/test_chief_ai_sprint.py` | ✎ modifié | Tests pro_accept passent l'auth pro_h (Sprint 14 requirement) |
| `server.py.backup_p1_bloc4` | 💾 backup | Point de restauration |

## 4. Lignes retirées de `server.py`

- Avant Bloc 4 : `3914` lignes
- Après Bloc 4 : `3625` lignes
- **Retirées ce bloc : `289` lignes**
- **Cumul Phase 1 (Bloc 1+2+3+4) : `−1142 lignes`** (de 4767 à 3625)

## 5. Machine d'états mise en place — `services/status_transitions.py`

3 tables : `BOOKING_TRANSITIONS`, `MISSION_TRANSITIONS`, `INTERVENTION_TRANSITIONS`. Chacune indexée par `(from_state, actor_role)` → set d'états cibles autorisés.

**Résumé Interventions** :
```
requested → cancelled (client) | accepted, declined (artisan)
assigned → cancelled (client) | accepted, declined (artisan)
accepted → cancelled (client|artisan) | professional_on_the_way (artisan)
professional_on_the_way → cancelled (both) | arrived (artisan)
arrived → in_progress (artisan)
in_progress → completed (artisan)
completed → validated | disputed (client)
```

**Transitions interdites (vérifiées par test)** :
- requested → completed ✗
- declined → in_progress ✗
- cancelled → completed ✗
- Client qui tente accept/start/finish → 403
- Utilisateur non-lié → 404 (aucun leak d'existence)

**Actor authz embedded** dans la table via la clé `(from, role)` — un même from/to peut être autorisé pour client mais interdit pour artisan.

**Retours HTTP** : 400 pour transition illégale (legacy contract), 409 réservé aux conflits concurrentiels (compare-and-set failed).

## 6. Contrôles d'ownership ajoutés

### Filtres Mongo composites
- **Bookings** : `st.actor_role_for(booking, user_id)` doit retourner "client" ou "artisan", sinon 404
- **Missions** : `client_id == user_id` (owner), pro_accept vérifie `artisan_row.user_id == user_id` (si non-null)
- **Interventions** : `_load_owned` teste `client_id` OR `artisan_user_id` → 404 sinon

### 404 uniforme (anti-enumeration)
Un utilisateur tiers reçoit toujours **404** (jamais 403) sur :
- GET /bookings/{id}, PATCH /bookings/{id}
- GET /missions/{id}
- GET /interventions/{id}, POST /interventions/{id}/cancel

### Compare-and-set atomique
Chaque transition d'état utilise :
```python
result = await db.X.update_one(
    {"id": x_id, "status": current_state},  # ← filter includes current
    {"$set": {"status": new_state, ...}},
)
if result.modified_count == 0:
    raise 409  # concurrent update caught
```

### /pro_accept — double protection anti-race
- Filter compare-and-set sur `accepted_by: None` → seule la première update réussit
- Toutes les tentatives concurrentes suivantes → 409 avec audit log `mission.accept_conflict`

### Audit logs
- `booking.created`, `booking.status.<new>`, `booking.access_denied` (tentatives illégitimes)
- `mission.created`, `mission.booked`, `mission.confirmed`, `mission.accepted`, `mission.no_pro`
- `mission.accept_denied` (raison : not_artisan | foreign_artisan_id | not_notified), `mission.accept_conflict`
- `intervention.requested`, `intervention.accepted`, `intervention.declined`, `intervention.cancelled`, `intervention.completed`

## 7. Résultats exacts des tests

### Nouveaux tests Bloc 4
| Test | Résultat |
|---|---|
| `test_sprint14_p1_bloc4_mission_flow.py` (22 tests) | **22/22 ✅** |

### Suite complète — 3 runs consécutifs (vérifiés par testing_agent iteration_21)
| Run | Passed | Skipped | Failed | Duration |
|---|---|---|---|---|
| 1 | **484/485** | 1 | 0 | 79.69s |
| 2 | **484/485** | 1 | 0 | 80.31s |
| 3 | **484/485** | 1 | 0 | 123.48s |

- ✅ Aucun échec, aucun flake
- ✅ Le seul skipped (`test_redeem_insufficient_400`) est pré-existant, sans rapport avec Bloc 4
- ✅ Zéro régression sur les 383+ tests baseline

## 8. Données encore simulées (`simulated: true` conservé)

| Endpoint / Champ | Marqueur |
|---|---|
| `POST /bookings` | `simulated: true` sur booking |
| `POST /missions` | `simulated: true`, `price_estimated: true` |
| `POST /missions/{id}/book` | `eta_simulated: true` |
| `POST /missions/{id}/confirm` | `eta_simulated: true` |
| `POST /missions/{id}/pro_accept` | `eta_simulated: true` |
| `GET /missions/{id}` (tracking) | `live_position_simulated: true` |
| `POST /interventions/request` | `simulated: true`, `price_simulated: true` |

## 9. Dette technique restante

1. **`services/status_transitions.py`** contient déjà les états `awaiting_validation`, `validated`, `disputed` prévus pour Bloc 5 (payments) — non testés encore.
2. **`_set_candidate`, `annotate_reviewed`, `_append_passport_history`** restaurés dans `server.py` — utilisés par des blocs non migrés (reviews, home-passport, complete). À sortir en `services/` lors de Bloc 5.
3. **`DepositIntentInput`, `DepositConfirmInput`, `_compute_deposit_cents`** restaurés dans `server.py` — restent nécessaires pour les endpoints deposit non migrés.
4. **Ownership pro_accept assouplie** : le check `artisan_row.user_id == user_id` est **skippé si `user_id is None`** (seeded artisans ont un user_id null). À reserrer une fois le seed backfillé.
5. **4 backups .py sur disque** (`backup_p1`, `_bloc2`, `_bloc3`, `_bloc4`) — à supprimer en fin de Phase 1.
6. **Import `bcrypt`** encore dupliqué (server.py + routes/auth + routes/security). À centraliser au Bloc 5 (payments).
7. **Doublon `get_current_user`** legacy dans server.py — inchangé pour ce bloc.

## 10. Risques identifiés & mitigés

| Risque | Sévérité | Mitigation appliquée |
|---|---|---|
| Cross-user booking modification | 🔴 Critique | `actor_role_for()` + 404 uniforme (test dédié) |
| Cross-artisan mission acceptance | 🔴 Critique | Filter `artisan_id ∈ notified_pros` + user_id check (log si null) |
| Double acceptance urgence | 🔴 Critique | Atomic compare-and-set sur `accepted_by: None` + 409 |
| pro_accept sans auth | 🔴 Critique | JWT header obligatoire (test `test_pro_accept_requires_auth`) |
| Client crée facture/garantie directement | 🔴 Critique | Ces endpoints restent dans `/missions/{id}/complete` hors Bloc 4, gated par payment status |
| Transitions d'état illogiques | 🟠 Haute | State machine centralisée + 400 uniforme |
| XSS dans description booking | 🟡 Moyenne | Refus `<script>`, max_length 2000 |
| ID invalide (path traversal) | 🟡 Moyenne | Regex `^[a-zA-Z0-9_\-]+$` sur artisan_id |
| Coordonnées GPS hors bornes | 🟡 Moyenne | Pydantic `ge=-90 le=90` |
| Simulé vs réel confusion | 🔴 Critique | `simulated:true` + `price_estimated:true` + `eta_simulated:true` partout |
| Bookings/missions tronquées à 500 sans sort | 🟠 Haute | Sort Mongo `created_at desc` avant `to_list` |
| Contrat API cassé | 🟠 Haute | Slot regex accepte HH:MM ET HH:MM-HH:MM (legacy) |

## Point de restauration

```bash
cp /app/backend/server.py.backup_p1_bloc4 /app/backend/server.py
rm /app/backend/routes/bookings.py /app/backend/routes/missions.py /app/backend/routes/interventions.py
rm /app/backend/services/status_transitions.py
rm /app/backend/tests/test_sprint14_p1_bloc4_mission_flow.py
sudo supervisorctl restart backend
```

---

**Statut Phase 1**
- ✅ Bloc 1 (auth + security) — 24 endpoints
- ✅ Bloc 2 (users + roles) — 7 endpoints
- ✅ Bloc 3 (artisans) — 22 endpoints
- ✅ Bloc 4 (bookings + missions + interventions) — 17 endpoints
- ⏸️ Bloc 5 (payments) — en attente de validation

**Total migré : 70 endpoints · `−1142` lignes de `server.py`**
