# ProConnect / Auxora — PRD

## Problem Statement (original, FR)
Application de mise en relation à la Uber/Airbnb connectant les clients (particuliers/pros) aux artisans des métiers manuels (plombier, chauffagiste, climaticien, peintre, serrurier, etc.). Les clients sélectionnent et réservent un artisan ; les sociétés/artisans paient l'accès pour être référencés. Interface fluide et intuitive façon Revolut.

**Pivot 2026-07** : passage du modèle marketplace pur au modèle **Home Operating System** — l'utilisateur revient chaque mois, pas seulement quand il a un problème.

## User choices
- MVP: les deux côtés (client + artisan)
- Auth: Email/mot de passe (JWT) + Google (Emergent)
- Paiement abonnement: SIMULÉ pour l'instant
- Mise en relation: le client réserve directement un créneau
- Design: dark premium + or champagne, Plus Jakarta Sans (inchangé après pivot)

## Personas
- Client: cherche un artisan, réserve, suit ses interventions, **gère ses biens et équipements**.
- Artisan/Pro: crée son profil, s'abonne pour être référencé, gère les demandes.

## Architecture
- Backend FastAPI (/api), MongoDB (motor). Bearer session_token (7j), bcrypt.
- 58 endpoints. Collections: users, user_sessions, artisan_profiles, bookings, conversations, missions, invoices, guarantees, home_passport, **properties, property_equipment, property_documents, property_reminders**.
- Frontend Expo Router. AuthContext. Thème /src/theme.
- Tabs client (5): Accueil, **Ma Maison**, Réservations, Messages, Profil.
- Tabs artisan: Tableau de bord, Mon profil, Abonnement.

## Implemented (2026-07 — Sprint FinTech / Stripe Connect)
### Payments & Escrow — Marketplace trusted third party
- **`services/payments.py`** : wrapper Stripe modulaire, mode `MOCK_MODE` auto (STRIPE_API_KEY placeholder → dev sans clés réelles ; vraie clé → prod immédiate, zéro refactor). SDK `stripe==14.4.1`.
- **Escrow state machine** (`pending → held → released|refunded|frozen`) : plateforme est tiers de confiance. Séparation "Charges and Transfers" — le client paie la plateforme, on retient jusqu'à validation, puis Transfer vers Connected Account net de commission.
- **Stripe Connect Express** : `POST /connect/onboard` génère lien d'onboarding, `GET /connect/status` synchronise l'état.
- **Paiements** : `POST /payments/create-intent` (booking → PaymentIntent avec automatic_payment_methods = card + Apple Pay + Google Pay). `POST /payments/{id}/mock-confirm` en dev ; en prod, webhook `payment_intent.succeeded` fait la transition.
- **Escrow ops** : `POST /escrow/{booking_id}/release|refund`, `POST /escrow/freeze` (owner ou admin ; gèle sur dispute).
- **Commissions configurables** avec précédence `exemption > promo > trade > global > default 1000 bps` : `GET/PUT /admin/commissions`, `POST/DELETE /admin/commission-rules` (kind = trade | promo | exemption). Floor `min_cents` 2€.
- **Subscriptions** : 3 plans (Starter 0€, Professional 29€/mois, Enterprise 79€/mois). `GET /subscriptions/plans` (public, safe), `POST /subscriptions/subscribe`, `POST /subscriptions/cancel` (cancel_at_period_end), `GET /subscriptions/mine`. **Le ranking ne dépend JAMAIS du plan** — matching.py 0 référence à subscription.
- **Dashboards** :
  - Admin : `GET /admin/finance/overview` (gross / commissions / refunds / MRR / pending_payouts / failed_payments / top_trades / active_subscriptions par plan).
  - Pro : `GET /artisans/me/finance` (revenue / gross / commissions / pending / transfers_count / monthly_evolution 6 mois / recent_transfers 10).
- **Webhooks** : `POST /api/stripe/webhooks` — idempotent via `stripe_events`. Handles `payment_intent.succeeded/payment_failed`, `charge.refunded`, `customer.subscription.updated/deleted`, `account.updated`.
- **Audit logs** : chaque transition (payment, refund, escrow, commission, subscription, connect) écrit dans `audit_logs`. `GET /admin/audit-logs?limit=N`.
- **Sécurité admin** : `require_admin` dépend de `ADMIN_EMAILS` env allow-list ou `role="admin"`. Non-admin → 403 sur `/admin/*`.
- **Future-ready** : `GET /payments/future-features` publie 5 produits en `coming_soon` (installments, BNPL, maintenance subscriptions, insurance, marketplace financing). Architecture prête, pas implémentés.
- **Tests** : 28/28 pytest `test_fintech_sprint.py` + 50/50 régression (My Home + Trust Engine) — GREEN.
- **Collections nouvelles** : `stripe_accounts`, `payments`, `escrows`, `transfers`, `refunds`, `subscriptions_records`, `platform_config`, `commission_rules`, `audit_logs`, `stripe_events`.

## Implemented (2026-07 — Sprint Trust Engine)
### AI Trust Engine — Heart of the platform (NOUVEAU)
- **`services/trust_engine.py`** : moteur modulaire, déterministe, ML-ready. 20 signaux pondérés (WEIGHTS somme = 100). Chaque facteur est une fonction pure séparée, `feature_vector()` produit le vecteur normalisé prêt pour un modèle ML.
- **Score 0-100 jamais éditable** : recalculé automatiquement à chaque hook (POST /reviews, PATCH /bookings, POST /disputes, POST /artisans/me). Persistance idempotente via `trust_engine.persist(db, artisan_id)`.
- **Signaux** : identity_verified, insurance_verified, business_registered, years_experience, customer_rating, jobs_completed, acceptance_rate, cancellation_rate, response_speed, arrival_time, punctuality, dispute_history, customer_satisfaction, completion_rate, recent_activity, availability, distance_relevance, speciality_match, emergency_capability, platform_loyalty.
- **Pénalités additives** : unresolved_dispute, resolved_severe/moderate/minor, recent_no_activity_60d, high_cancellation_20p.
- **Endpoints backend (8 nouveaux)** :
  - `GET /api/artisans/{aid}/trust` — breakdown complet
  - `GET /api/artisans/{aid}/confidence-card` — carte client-safe (verified/insured/reasons FR/badges)
  - `GET /api/artisans/{aid}/badges` — badges calculés
  - `GET /api/artisans/me/scoreboard` — pro-only : strengths + improvements + recos FR
  - `POST /api/artisans/{aid}/recompute-trust` — recompute idempotent
  - `POST /api/disputes` — auto-pénalité par sévérité (minor/moderate/severe). Sévère → requires_manual_review, jamais de ban auto.
  - `GET /api/disputes/mine` — liste selon rôle (client=opened / artisan=against)
  - `POST /api/matching/smart-recommendations` — alternatives (higher_rated/faster/closer/cheaper/earlier_slot)
- **Enrichissement automatique** : `GET /api/artisans/{aid}` retourne désormais `trust_score`, `confidence_card`, `badges` — pas de nouveau écran nécessaire côté UI, la carte de confiance existante s'enrichit.
- **Badges** : verified, insured, background_checked, premium (trust≥95), top_rated (rating≥4.8, gold), emergency_expert (gold), fast_response (silver), jobs_bronze/silver/gold/platinum (25/100/500/1000 missions, mutuellement exclusifs), highly_recommended (gold), loyal_partner (12+ mois).
- **Backfill idempotent** au démarrage : 12 artisans mis à jour avec les nouveaux signaux + recompute automatique.
- **Tests** : 23/23 pytest `test_trust_engine.py` + 27/27 régressions `test_my_home.py` — GREEN.

## Implemented (2026-07 — Sprint My Home)
### Ma Maison — Home Operating System (NOUVEAU)
- **Multi-biens** : 5 types (apartment, house, office, commercial, vacation). Photos base64, adresse, surface, année, notes.
- **Property Dashboard** : hero image + gradient scrim, quick actions (Équipements/Documents/Timeline/Rappels), carte insights santé %, entretiens à venir, équipements récents, cartes IA "Bientôt disponible".
- **Équipements** : 14 catégories (chaudière, chauffe-eau, PAC, tableau élec, clim, VMC, toit, fenêtres, portes, détecteurs, solaire, borne VE, adoucisseur, autre). Marque, modèle, N° série, installateur, dates installation/garantie, statut (ok/attention/maintenance/replace), notes, photos, documents liés.
- **Documents (Passeport numérique)** : 8 catégories (factures, garanties, manuels, certificats, plans, photos, rapports, autres). Filtres par catégorie.
- **Timeline agrégée** : équipements installés + documents ajoutés + interventions (bookings.property_id) + rappels terminés, groupés par année.
- **Insights** : équipements OK / à surveiller, documents, upcoming maintenance, interventions, argent investi, santé moyenne %. Valeurs de démo réalistes quand vide.
- **Rappels** : architecture prête (upcoming/due/done/snoozed), suggestions rapides, fréquences (once/monthly/quarterly/biannual/yearly). Pas de notifs (à venir).
- **IA placeholders** : 6 cartes "Bientôt disponible" (Santé équipements, Maintenance prédictive, Détection risques, Optimisation énergétique, Expiration garanties, Inspection recommandée).
- **Sécurité** : toutes les routes /properties requièrent Bearer, 401/404 propres.

### Phase 4 — Couche d'intelligence backend (architecte IA)
- Moteur de matching pondéré `services/matching.py`: score 0-100 + `match_reasons` FR — affichés sur écran matching.
- Mode Urgence: broadcast top 5 pros, premier qui accepte gagne.
- Architecture sync calendrier MOCKÉE `services/calendar_sync.py`.
- Modèles: complete_mission génère facture + garantie 12 mois + entrée Home Passport.

### Phase 3 — AI-first premium pivot
- Design premium DARK + accents OR CHAMPAGNE, Plus Jakarta Sans.
- Bouton "J'ai un problème" + écran Diagnostic IA (texte + photos + voix via Whisper).
- Matching IA automatique, Trust Score par artisan, clé universelle Emergent (GPT-4o + Whisper).

### Phase 1 & 2
- Auth email/password + Google (Emergent), rôles client/artisan.
- 12 catégories, 12 artisans seedés.
- Client: home, liste/recherche artisans, fiche + réservation créneau, mes réservations.
- Artisan: dashboard, édition profil, abonnement Premium simulé.

## Backlog
- P1: Lier bookings/interventions à property_id via l'UI (déjà supporté côté schema).
- P1: Upload documents réels (base64 file), stockage S3.
- P1: Vraie intégration Stripe Connect (paiement + escrow + commission).
- P1: Messagerie temps réel (WebSocket), avis réels après mission.
- P2: Réelle IA sur les 6 cartes "Bientôt" (santé, maintenance prédictive, risques…).
- P2: Notifications réelles sur rappels d'entretien (push).
- P2: Dashboard admin, GPS artisan réel, mode Urgence multi-pros polish.

## Next tasks
- Attacher les interventions du diagnostic IA à un bien sélectionné.
- Rendre 3 des 6 cartes IA fonctionnelles (santé équipement calculé, expiration garanties, inspection recommandée).
- Notifications push sur rappels.
