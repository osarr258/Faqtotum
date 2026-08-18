# Inventaire des routes legacy dans `backend/server.py` — V1

Date : Juin 2026 · Contexte : préparation V1 production Faqtotum.
Total : **144 routes** encore dans `server.py`, à comparer aux **60+ routes** déjà modularisées dans `backend/routes/`.

**Aucun doublon exact détecté** avec les modules déjà migrés (`auth`, `users`, `artisans`, `bookings`, `missions`, `interventions`, `security`). Les 144 routes ci-dessous couvrent des domaines fonctionnels distincts.

---

## Groupement par domaine fonctionnel

### 🔷 A. CORE V1 — À migrer (indispensables au fonctionnement de l'app)

| # | Routes | Fichier cible proposé |
|---|--------|----------------------|
| A1 | **Discovery** — GET `/categories`, `/artisans/nearby` | `routes/artisans.py` (extension) |
| A2 | **Reviews** — POST `/reviews`, GET `/reviews/artisan/{id}` | `routes/reviews.py` (nouveau) |
| A3 | **Messaging** — GET `/conversations`, GET `/conversations/{id}`, POST `/conversations/{id}/messages` | `routes/messaging.py` (nouveau) |
| A4 | **AI / Concierge** — 9 routes : `/ai/diagnose`, `/ai/transcribe`, `/concierge/*` | `routes/ai.py` (nouveau) |
| A5 | **Properties CRUD** — GET/POST/PATCH/DELETE `/properties[/{pid}]` (5 routes) | `routes/properties.py` (nouveau) |
| A6 | **Property Equipment** — 5 routes CRUD | `routes/properties.py` |
| A7 | **Property Documents** — 3 routes | `routes/properties.py` |
| A8 | **Property Reminders** — 4 routes | `routes/properties.py` |
| A9 | **Property Timeline / Insights / AI Cards** — 3 routes | `routes/properties.py` |
| A10 | **Property Events / Auto Reminders** — 4 routes | `routes/properties.py` |
| A11 | **Property Budget** — GET `/properties/{pid}/budget` | `routes/properties.py` |
| A12 | **Payments (client)** — POST `/payments/create-intent`, `/payments/{id}/mock-confirm`, GET `/escrows/mine`, POST `/escrow/*` (6 routes) | `routes/payments.py` (nouveau) |
| A13 | **Interventions Payments Flow** — 7 routes critiques : deposit/create+confirm, start/finish, final/create+confirm, validate, payment-summary | `routes/payments.py` |
| A14 | **Stripe Connect (payouts artisan)** — POST `/connect/onboard`, GET `/connect/status` | `routes/payments.py` |
| A15 | **Admin** — 6 routes : finance/overview, commissions, commission-rules, audit-logs | `routes/admin.py` (nouveau) |

**Sous-total à migrer :** ~63 routes réparties sur ~7 nouveaux modules.

---

### 🟡 B. POTENTIELLEMENT V1 — À valider avec toi

Ces routes correspondent à des fonctionnalités déjà codées mais dont on peut légitimement se demander si elles doivent être présentes dès la V1 ou reportées à V1.1+.

| # | Routes | Question à trancher |
|---|--------|---------------------|
| B1 | **Trust / Confidence Cards** — 4 routes (`/artisans/{id}/trust`, `/confidence-card`, `/badges`, `/recompute-trust`) | Système de badges de confiance — cœur de la différenciation ? |
| B2 | **Disputes** — 2 routes (`POST /disputes`, `GET /disputes/mine`) | Gestion des litiges — obligatoire pour paiements réels ? |
| B3 | **Smart Matching** — POST `/matching/smart-recommendations` | Recommandation IA d'artisans |
| B4 | **Trusted Pros** — 3 routes (favoris artisans) | Feature nice-to-have |
| B5 | **Favourites** — 3 routes (favoris généraux) | Feature nice-to-have |
| B6 | **Analytics** — GET `/analytics/mine` | Dashboard perso utilisateur |
| B7 | **Home Passport / Invoices / Guarantees** — 4 routes | Feature vitrine ("passeport numérique") |
| B8 | **Subscriptions** — 4 routes (plans, subscribe, cancel, mine) | Model B2B seul ? Ou B2C aussi ? |
| B9 | **Property Sharing / Public Passport** — 3 routes | Partage lien public passeport |
| B10 | **Missions extras** — POST `/missions/{id}/complete` | Complétion legacy — probablement duplicate de flow interventions |

**Sous-total à trancher :** ~29 routes

---

### 🔴 C. REPORT V1.x — Suggestion de suppression / mise en pause pour la V1

Fonctionnalités "grandes ambitions" (B2B Enterprise + réseau social) qui semblent surdimensionnées pour une V1 grand-public. À valider explicitement.

| # | Routes | Justification suppression |
|---|--------|--------------------------|
| C1 | **Organizations (Enterprise B2B)** — 11 routes complètes : CRUD orgs, members, properties, dashboard, analytics, map, documents, integrations | Feature enterprise complexe — inutile pour lancement grand-public V1 |
| C2 | **Work Orders (Enterprise)** — 4 routes | Idem, dépendance Organizations |
| C3 | **Enterprise Meta** — GET `/enterprise/roles`, `/enterprise/account-types` | Idem |
| C4 | **Pro Hub** — 4 routes (`/pro/dashboard`, `/pro/coach`, `/pro/insights`, PATCH `/pro/profile`) | Peut être remplacé par un profil artisan simple pour V1 |
| C5 | **Community / Social** — 7 routes (feed, posts, likes, bookmarks, comments, follow) | Réseau social interne — feature v2 |
| C6 | **Academy** — 2 routes (categories, cards) | Contenu pédagogique — v2 |
| C7 | **Marketing modules** — 2 routes | Feature interne inutile en V1 |
| C8 | **Loyalty / Referrals / Growth** — 6 routes (loyalty summary/ledger/redeem, referrals mine/redeem, growth levels) | Gamification — v2 possible |
| C9 | **Business (small biz setup)** — 2 routes | Peut être remplacé par simple checkbox rôle "pro" |
| C10 | **Property Members (co-propriété)** — 3 routes | Multi-utilisateurs par bien — v2 |
| C11 | **Property Health / Maintenance Plans auto** — 3 routes | Génération auto plan entretien — nice-to-have v2 |
| C12 | **Payments meta** — GET `/payments/future-features` | Route de dead-copy |

**Sous-total à supprimer :** ~52 routes

---

## Résumé chiffré

| Catégorie | Routes | % |
|---|---|---|
| 🔷 A. Core V1 (migrer) | 63 | 44% |
| 🟡 B. À valider | 29 | 20% |
| 🔴 C. Suggestion suppression V1 | 52 | 36% |
| **Total** | **144** | **100%** |

**Impact estimé si toutes les suggestions C sont validées :**
- `server.py` passerait de ~3626 lignes à ~1400 lignes (–61%)
- Réduction de la surface d'attaque et du besoin de test de ~1/3
- Suppression de ~10 fichiers `services/*.py` (enterprise.py, pro_hub.py, community.py, academy.py, loyalty.py, referrals.py, growth.py, business.py, marketing.py, property_members.py)
- ~40 fichiers frontend potentiellement supprimables

---

## Ce qui reste à faire avant la migration effective

1. **Validation utilisateur** de la classification A / B / C ci-dessus
2. Après validation :
   - Migration des routes catégorie A vers `backend/routes/{properties,payments,admin,ai,messaging,reviews}.py` (pattern Strangler comme les autres)
   - Suppression des routes catégorie C + services associés + écrans frontend + tests obsolètes
   - Trace de suppression dans `memory/v1_removed_features.md` pour référence future
3. Run complet de la suite de tests après chaque batch pour zéro régression.
