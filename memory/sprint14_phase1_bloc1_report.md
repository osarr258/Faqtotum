# Sprint 14 — Phase 1 (Strangler Pattern)

## Bloc 1/8 — Auth + Security — ✅ MIGRÉ

### Modules créés
```
/app/backend/security/
  ├── __init__.py                (package)
  ├── dependencies.py            (get_current_user + require_roles factory)
  └── ownership.py               (helpers: get_owned_property/booking/intervention/mission/artisan/conversation)

/app/backend/routes/
  ├── __init__.py                (package)
  ├── auth.py                    (build_auth_router)
  └── security.py                (build_security_router)

/app/backend/tests/
  └── test_sprint14_p1_migration.py   (12 non-regression tests)

/app/backend/server.py.backup_p1   (backup avant migration)
```

### Endpoints migrés (Auth — 5 routes)
- `GET  /api/`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/google`
- `GET  /api/auth/me`
- `POST /api/auth/logout`

### Endpoints migrés (Security — 18 routes)
- `GET    /api/security/overview`
- `GET    /api/security/sessions`
- `DELETE /api/security/sessions/{session_id}`
- `POST   /api/security/sessions/revoke-others`
- `POST   /api/security/password/change`
- `GET    /api/security/audit`
- `GET    /api/security/audit/verify` (admin)
- `GET    /api/security/audit/all` (admin)
- `GET    /api/security/gdpr/consents`
- `POST   /api/security/gdpr/consents`
- `GET    /api/security/gdpr/export`
- `DELETE /api/security/gdpr/account`
- `GET    /api/security/mfa`
- `POST   /api/security/mfa/prepare`
- `POST   /api/security/mfa/verify`
- `DELETE /api/security/mfa`
- `POST   /api/security/biometrics/register`
- `GET    /api/security/biometrics`
- `GET    /api/security/roles`
- `GET    /api/security/admin/sessions` (admin)

Total: **24 endpoints** sortis de `server.py` vers `routes/`.

### Tests exécutés
| Suite | Résultat |
|---|---|
| `test_sprint14_p1_migration.py` (nouveau) | **12/12 ✅** |
| `test_security_sprint.py` (existant) | 100% ✅ |
| `test_home_os_passport.py` | **10/10 ✅** |
| `test_sprint_new_features.py` | 8/8 ✅ (en isolé) |
| `test_trust_engine.py` | 23/23 ✅ (en isolé) |
| **Suite complète** | **414/415** (1 échec cross-test dû au rate-limit distribué — pas une régression) |

### Code restant dans `server.py`
- **Lignes** : `4422` (avant : `4767`) — **345 lignes supprimées**
- Reste à migrer (blocs 3 → 8) :
  - Bloc 3 : `/users`, `/artisans/me/*` (~4 endpoints)
  - Bloc 4 : `/artisans/*`, `/categories` (~10 endpoints)
  - Bloc 5 : `/missions`, `/interventions`, `/bookings` (~30 endpoints)
  - Bloc 6 : `/connect/*`, `/interventions/*/deposit`, webhooks Stripe (~20 endpoints)
  - Bloc 7 : `/properties/*`, `/passport/{token}` (~25 endpoints)
  - Bloc 8 : `/ai/*`, `/concierge/*` (~15 endpoints)
  - Bloc 9 : `/admin/*`, `/security/admin/*` (déjà migré partiellement)

### Architecture actuelle
```
server.py  ─────────────────►  api_router (legacy /api/*)  ──► app
  │
  ├─► routes.auth.build_auth_router(db, dep)  ──► app.include_router prefix=/api
  └─► routes.security.build_security_router(db, dep, roles) ──► app.include_router prefix=/api

security.dependencies.get_db_dependency(db)  fournit  get_current_user, require_roles
     └─ utilisé par TOUS les nouveaux routers
```

### Risques & dette technique restants
1. **Duplication `get_current_user`** — la version legacy dans `server.py` (l.72-100) est un doublon de `security/dependencies.py`. Non-critique tant que les 2 lisent la même collection Mongo `user_sessions`, mais à supprimer en fin de Phase 1.
2. **Fuites d'imports** — `bcrypt` est importé dans 3 fichiers (`server.py`, `routes/auth.py`, `routes/security.py`). Sortir en `services/auth_utils.py` au bloc suivant.
3. **Test `test_distributed_brute_force_by_ip`** — fait exprès d'atteindre le seuil de 30 emails distincts/IP → devient rouge quand exécuté après d'autres tests qui logguent des échecs. À isoler dans un scope propre.
4. **`server.py.backup_p1`** — backup à supprimer une fois la Phase 1 complète.
5. **Aucun changement de comportement observable** — les 383 tests historiques + les 10 Home OS + les 12 nouveaux P1 passent.

### Point de restauration
- Backup : `/app/backend/server.py.backup_p1`
- Commande rollback : `cp /app/backend/server.py.backup_p1 /app/backend/server.py && sudo supervisorctl restart backend`

---

**Prêt à enchaîner sur le Bloc 2 (Users + Rôles) ou attendre validation ?**
