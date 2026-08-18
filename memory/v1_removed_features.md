# V1 — Fonctionnalités retirées

Date : Juin 2026
Contexte : Nettoyage V1 pour production. Cible : grand public (B2C).
Critères appliqués (voir prompt utilisateur du 2026-06) : pas d'écran frontend + pas de touche argent/auth + pas de parcours core → SUPPRIMER. Enterprise/B2B lourd → SUPPRIMER (hors cible V1).

## Résumé chiffré

| Avant | Après | Delta |
|---|---|---|
| `server.py` : 3678 lignes | `server.py` : 2504 lignes | **−1174 lignes (−32%)** |
| 144 routes legacy dans `server.py` | 72 routes legacy restantes | **−72 routes (−50%)** |
| 508 tests | 267 tests | −241 tests obsolètes |

## Blocs supprimés (backend)

### 1. Home Passport (Q4)
- `GET /home-passport`
- `POST /home-passport/equipment`
- `GET /invoices/mine`
- `GET /guarantees/mine`
- **Motivation** : doublonne avec `/properties/*` (CRUD + share + passport public via token) déjà gardés. Aucun écran frontend dédié.
- **Fichiers** : `server.py`
- **Pour restaurer** : `git show HEAD~1:backend/server.py | sed -n '840,876p'`

### 2. Trust Engine endpoints (Q1)
- `GET /artisans/{id}/trust`
- `GET /artisans/{id}/confidence-card`
- `GET /artisans/{id}/badges`
- `POST /artisans/{id}/recompute-trust`
- **Conservé** : le champ `trust_score` sur `/artisans/{id}`, le service `services/trust_engine.py` (utilisé en interne par bookings/reviews). Recalcul en cron possible.
- **Motivation** : aucun appel frontend, doublonne le champ trust_score exposé sur `/artisans/{id}`.
- **Fichiers** : `server.py`, `tests/test_trust_engine.py` (supprimé — 23 tests).

### 3. Smart Matching
- `POST /matching/smart-recommendations`
- **Motivation** : jamais appelé par le frontend, `/missions/{id}` retourne déjà des recommandations classées.
- **Fichiers** : `server.py` (+ Pydantic `SmartRecoInput`).

### 4. Growth / Gamification (7 routes)
- `GET /trusted-pros`, `POST /trusted-pros`, `DELETE /trusted-pros/{id}`
- `GET /loyalty/summary`, `GET /loyalty/ledger`, `POST /loyalty/redeem`
- `GET /referrals/mine`, `POST /referrals/redeem`
- `GET /growth/levels`
- **Motivation** : réseau-effet, inutile en pré-lancement. Réactivable dès qu'il y a une base d'utilisateurs.
- **Fichiers** : `server.py`, `tests/test_growth_sprint.py` (supprimé — 49 tests).
- **Note** : le service `services/growth.py` est conservé (contient `pro_level`, `loyalty_tier`, `health_label`, `suggest_maintenance` utilisés par le Property Health Q6 conservé en B).

### 5. Business Accounts (Q3 partiel)
- `POST /business/setup`, `GET /business/mine`
- **Motivation** : rôle "pro/particulier" géré par un flag simple sur `users.role` — pas besoin d'un système dédié en V1.

### 6. Family Sharing / Property Members (Q5)
- `GET /properties/{pid}/members`, `POST /properties/{pid}/members`, `DELETE /properties/{pid}/members/{id}`
- **Motivation** : feature multi-utilisateurs sur bien immobilier, UX complexe (droits, invitations). Report V1.x.

### 7. Favourites (3 routes)
- `GET /favourites`, `POST /favourites`, `DELETE /favourites/{id}`
- **Motivation** : nice-to-have, aucun écran frontend.

### 8. Customer Analytics
- `GET /analytics/mine`
- **Motivation** : dashboard perso non-prioritaire, trivial à re-builder.

### 9. Enterprise B2B (17 routes) ⚠️ gros bloc
- Organizations : 11 routes (`/organizations/*` CRUD + members + properties + dashboard + analytics + map + documents + integrations)
- Work Orders : 4 routes (`/work-orders*`)
- Enterprise meta : 2 routes (`/enterprise/roles`, `/enterprise/account-types`, `/integrations/available`)
- **Motivation** : cible V1 confirmée = grand public B2C. Feature enterprise = pivot v2 si demande client.
- **Fichiers** : `server.py`, **`services/enterprise.py` (supprimé, ~500 lignes)**, `tests/test_enterprise_sprint.py` (supprimé — 40+ tests).

### 10. Pro Hub + Community + Academy + Marketing (15 routes) ⚠️ gros bloc
- Pro Hub : `/pro/dashboard`, `/pro/coach`, `/pro/insights`, PATCH `/pro/profile` (4)
- Community : feed, posts, likes, bookmarks, comments, follow, bookmarks/mine (7)
- Academy : `/academy/categories`, `/academy/cards` (2)
- Marketing : `/marketing/modules`, `POST /marketing/{key}/interest` (2)
- **Motivation** : réseau social interne + contenus pédagogiques = v2.
- **Fichiers** : `server.py`, **`services/pro_hub.py` (supprimé, ~600 lignes)**, `tests/test_pro_hub.py` (supprimé — 30+ tests).

### 11. Subscriptions plateforme (Q3)
- `GET /subscriptions/plans`, `POST /subscriptions/subscribe`, `POST /subscriptions/cancel`, `GET /subscriptions/mine`
- **Conservé** : `/artisans/me/subscribe` (dans `routes/artisans.py`) — endpoint spécifique artisan qui est encore utilisé côté frontend.
- **Motivation** : monétisation post-V1 à définir.
- **Fichiers** : `server.py`, tests dans `test_fintech_sprint.py` (6 tests supprimés par pruning).

### 12. Payments meta
- `GET /payments/future-features`
- **Motivation** : route dead-copy (juste un catalogue statique).

## Fichiers services conservés

| Fichier | Statut | Justification |
|---|---|---|
| `services/matching.py` | KEEP | Ranking des artisans (/missions/*) |
| `services/status_transitions.py` | KEEP | State machine bookings/missions/interventions |
| `services/trust_engine.py` | KEEP | Computation interne du trust_score |
| `services/growth.py` | KEEP (partiel) | health_label + suggest_maintenance (Q6 reporté) |
| `services/homes.py` | KEEP | Property CRUD + budget + public passport |
| `services/payments.py` | KEEP | Stripe integration |
| `services/paypal.py` | KEEP | PayPal integration |
| `services/concierge.py` | KEEP | AI chat |
| `services/security.py` | KEEP | Sessions + MFA + audit |
| `services/calendar_sync.py` | KEEP | Availability artisans |
| `services/enterprise.py` | **DELETED** | Enterprise B2B hors périmètre V1 |
| `services/pro_hub.py` | **DELETED** | Pro Hub / Community v2 |

## Reportés (catégorie B — restent en place, non migrés, à traiter post-V1)

| Bloc | Routes | Prochaine étape |
|---|---|---|
| **Q2 Disputes** (litiges) | `POST /disputes`, `GET /disputes/mine` | Obligatoire dès activation Stripe live (chargebacks) |
| **Q6 Property Health / Maintenance-plan** | `GET /properties/{pid}/health`, `/maintenance-plan`, `POST /maintenance-plan/generate-reminders` | À réactiver dès qu'un écran maintenance-plan.tsx sera fait |

## Fichiers frontend supprimés
Aucun — les fonctionnalités supprimées n'avaient pas d'écran (c'est justement pour ça qu'elles ont été retirées).

## Pour restaurer une fonctionnalité

Toutes les suppressions sont conservées dans l'historique git. Pour restaurer :
```bash
git log --oneline -- backend/server.py  # trouver le commit "V1 prune"
git show <commit>^:backend/server.py > /tmp/server_old.py
# copier/coller le bloc souhaité, tester, commit
```

Backup local également disponible à `/app/backend/server.py.pre_v1_prune` (temporaire, à supprimer après validation).
