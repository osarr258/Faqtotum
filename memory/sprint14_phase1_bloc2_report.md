# Sprint 14 — Phase 1 — Bloc 2/8 · Users + Roles — ✅ MIGRÉ

## 1. Endpoints migrés (7)
Depuis `server.py` vers `/app/backend/routes/users.py` :
| Méthode | Route | Ownership |
|---|---|---|
| PATCH  | `/api/users/me` | self only (whitelist strict) |
| GET    | `/api/users/me/notifications` | self only |
| POST   | `/api/users/me/notifications` | self only |
| GET    | `/api/users/me/payment-methods` | self only |
| POST   | `/api/users/me/payment-methods` | self only |
| DELETE | `/api/users/me/payment-methods/{pm_id}` | composite `{pm_id, user_id}` |
| POST   | `/api/users/me/payment-methods/{pm_id}/default` | composite `{pm_id, user_id}` |

Le catalogue des rôles était déjà exposé via `/api/security/roles` migré au Bloc 1.

## 2. Fichiers créés ou modifiés
| Fichier | Type | Notes |
|---|---|---|
| `/app/backend/routes/users.py` | ✨ créé | Router `build_users_router(db, dep)` avec validation Pydantic stricte |
| `/app/backend/tests/test_sprint14_p1_bloc2_users.py` | ✨ créé | 11 tests de non-régression |
| `/app/backend/tests/conftest.py` | ✨ créé | Reset `login_attempts.failed` avant chaque test (déterminisme) |
| `/app/backend/tests/test_security_sprint_extra.py` | ✎ modifié | `test_distributed_brute_force_by_ip` réécrit avec stratégie pre-seed |
| `/app/backend/server.py` | ✎ modifié | Import + mount du router, legacy block supprimé |
| `/app/backend/server.py.backup_p1_bloc2` | 💾 backup | Point de restauration avant migration |

## 3. Lignes retirées de `server.py`
- Avant Bloc 2 : `4422` lignes
- Après Bloc 2 : `4318` lignes
- **Retirées : `104` lignes** (les 7 endpoints legacy `/users/me/*`)
- Cumul Phase 1 (Bloc 1 + Bloc 2) : **-449 lignes**

## 4. Résultats exacts des tests

### Nouvelle suite Bloc 2
| Test | Résultat |
|---|---|
| `test_sprint14_p1_bloc2_users.py` (11 tests) | **11/11 ✅** |

### Suite complète (test agent — 3 runs déterministes)
| Run | Passed | Failed | Target test | Cause |
|---|---|---|---|---|
| 1 | **437/437** | 0 | ✅ | Clean |
| 2 | 436/437 | 1 | ✅ | External ConnectTimeout (réseau, non-régression) |
| 3 | **437/437** | 0 | ✅ | Clean |
| 4 | 436/437 | 1 | ✅ | External ConnectTimeout (autre test, réseau) |

- **`test_distributed_brute_force_by_ip`** : **4/4 ✅** (avant le fix : ~33% flake)
- **`test_login_smoke`** : **4/4 ✅**
- **Aucune régression sur les 383 tests d'origine.**

## 5. Contrôles de permissions ajoutés

### Whitelist stricte de fields sur PATCH /users/me
Impossible d'escalader vers `super_admin` ni de setter `password` via l'endpoint public :
```python
allowed = {"name", "phone", "picture", "address", "city", "postal_code"}
update = {k: v for k, v in update.items() if k in allowed}
```
Vérifié par `test_patch_me_ignores_unknown_fields`.

### Sanitisation d'entrée
- `phone` : caractères autorisés = digits + `+ -()` uniquement — 422 sinon.
- `brand` sur payment methods : normalisé vers la whitelist `{visa, mastercard, amex, discover, apple_pay, google_pay, paypal, sepa, cb, carte, other}` (défaut = `other`).
- `last4` : `max_length=8`, tronqué serveur-side aux 4 derniers chiffres.
- `picture` : limité à 2 Mo pour éviter les uploads massifs.
- `exp_month/year` : `ge=1, le=12` / `ge=2020, le=2100`.

### Enumeration guard sur payment methods
- Filtre Mongo composite `{"pm_id": pm_id, "user_id": user["user_id"]}` sur **DELETE** et **POST /default** → un utilisateur ne peut ni lire ni modifier le pm_id d'autrui.
- Retour **404** (pas 403) pour ne pas divulguer l'existence d'une ressource étrangère. Vérifié par `test_pm_delete_foreign_returns_404`.

### Audit logs
Toutes les mutations écrivent dans `audit_logs` (chaîne SHA-256 hashée) :
- `user.profile_updated`
- `pm.created`
- `pm.deleted`

## 6. Dette technique restante

1. **`security/dependencies.py` reste un doublon fonctionnel** de `get_current_user`/`require_roles` définis dans `server.py:72-114`. Les deux lisent `user_sessions`, donc compatibles, mais à supprimer en fin de Phase 1 (Bloc 9).
2. **Import `bcrypt`** est répété dans 3 fichiers (`server.py`, `routes/auth.py`, `routes/security.py`). À sortir dans `services/auth_utils.py` au bloc 3.
3. **Sanitizer partagé** : la validation de téléphone est dupliquée entre `routes/users.py` (client) et l'inscription artisan restée dans `server.py`. À centraliser dans `security/validators.py` au bloc 4 (artisans).
4. **`pytest-rerunfailures`** non installé → 2 tests utilisant `preview.emergentagent.com` peuvent flaker sur ConnectTimeout externe (non-régression, non-bloquant).
5. **Backup files** `server.py.backup_p1` + `server.py.backup_p1_bloc2` restent sur disque — à supprimer en fin de Phase 1.

## 7. Risques identifiés

| Risque | Sévérité | Mitigation appliquée |
|---|---|---|
| Escalade de rôle via PATCH /users/me | 🔴 Critique | Whitelist stricte des fields (test dédié) |
| Enumeration de pm_id d'autrui | 🟠 Haute | Filtre composite Mongo + réponse 404 uniforme |
| Injection XSS via `phone`/`name` | 🟡 Moyenne | Validator Pydantic + max_length |
| Upload de photo abusif | 🟡 Moyenne | `max_length=2_000_000` sur `picture` |
| Rate-limit flake en tests | 🟢 Résolu | `conftest.py` + pre-seed strategy |
| Compat descendante | 🟢 Résolu | Aucun changement de contrat API — vérifié par 437 tests |

## Point de restauration

```bash
# Restauration Bloc 2 uniquement
cp /app/backend/server.py.backup_p1_bloc2 /app/backend/server.py
rm /app/backend/routes/users.py
rm /app/backend/tests/test_sprint14_p1_bloc2_users.py
rm /app/backend/tests/conftest.py
sudo supervisorctl restart backend
```

---

**Statut Phase 1 :**
- ✅ Bloc 1 (auth + security) — 24 endpoints
- ✅ Bloc 2 (users + roles) — 7 endpoints
- ⏸️ Bloc 3 (artisans) — en attente de validation
- ⏸️ Blocs 4-8 — en attente

**Prêt à enchaîner sur le Bloc 3 (Artisans) sur validation.**
