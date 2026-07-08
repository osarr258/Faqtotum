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

## Implemented (2026-07 — Sprint Professional Hub)
### Le HQ digital de chaque pro (17 endpoints, 41 tests)
- **`services/pro_hub.py`** : Academy content (7 catégories + 7 cards `coming_soon`), Marketing modules stubs (5 tools), AI Business Coach déterministe (`coach_recommendations()`) qui combine breakdown du Trust Engine + milestones (25/100/500/1000 jobs + trust 90+), et `profile_completion()` pondéré (13 checks, 100 points).
- **Pro Dashboard** : `GET /pro/dashboard` agrège 16 métriques (today's jobs, upcoming, revenue total + monthly, growth_pct 30j vs 30j-60j, trust_score + level, pro_level Bronze/Silver/Gold/Platinum/Elite avec progress %, satisfaction, response_rate, avg_response_min, profile_completion breakdown, pending_documents, unread_messages, badges, top 3 coach recos).
- **Profil enrichi** : `PATCH /pro/profile` — logo/cover/services/areas_covered/opening_hours/certifications/languages/website/social. Recompute Trust auto. Retourne le profil + `profile_completion` (checks_count, checks_ok, missing[]).
- **AI Business Coach** : `GET /pro/coach` — jusqu'à 6 recos personnalisées classées par impact desc, avec milestones badges + trust.
- **Business Insights** : `GET /pro/insights` — revenue_evolution (12 mois), customer_growth (90j), unique_clients, repeat_clients (>1 booking), avg_job_value_cents, acceptance/cancellation/completion rates, top_cities top 5.
- **Community Feed** : 4 kinds (project/tip/question/achievement) + likes/bookmarks/follows idempotent (toggle) + comments. Auteur enrichi avec name/photo/trade auto. Photos capped 6, tags capped 5.
  - `GET /community/feed` (avec `liked_by_me` + `bookmarked_by_me`)
  - `POST /community/posts` (artisan-only)
  - `POST /community/posts/{id}/like|bookmark` (idempotent toggle)
  - `GET/POST /community/posts/{id}/comments`
  - `POST /community/follow/{user_id}` (400 self-follow)
  - `GET /community/bookmarks/mine`
- **Academy** : `GET /academy/categories` + `GET /academy/cards?category=` — architecture prête pour vrais contenus.
- **Marketing** : `GET /marketing/modules` + `POST /marketing/{key}/interest` — waitlist idempotente pour futurs modules payants.
- **Portfolio enrichissement** : `PATCH /artisans/me/gallery/{project_id}` — extend gallery avec description/city/duration_hours/completed_at/review_id.
- **Collections nouvelles** : `community_posts`, `community_comments`, `community_likes`, `community_bookmarks`, `community_follows`, `marketing_interests`.
- **Tests** : 41/41 pytest `test_pro_hub.py` + 237/237 régression = **278/278 GREEN**.

## Implemented (2026-07 — Sprint Enterprise / B2B)
### Multi-tenant, RBAC, Work Orders — one app pour B2C et B2B
- **`services/enterprise.py`** : ACCOUNT_TYPES (6), ORG_TYPES (12), TEAM_ROLES (7), matrice PERMISSIONS déclarative avec 20 actions (org.update, team.invite, work_order.approve/reject/complete/cancel, documents.upload/delete, analytics.view, invoices.pay, integrations.configure...), WORK_ORDER_STATUSES (7), WORK_ORDER_TRANSITIONS état-machine strict.
- **24 nouveaux endpoints** (total backend : **142 routes**) :
  - **Organizations** : POST/GET mine/PATCH `/organizations`
  - **Team members** : GET/POST/PATCH/DELETE avec RBAC
  - **Property linking** : `POST /organizations/{oid}/properties/link` + `GET /organizations/{oid}/properties`
  - **Work Orders** : POST create (employee→pending_approval auto, sinon draft), GET list (multi-org auto scoping), GET one, `POST /work-orders/{woid}/transition` (validation workflow + permission par status)
  - **Business Dashboard** : `GET /organizations/{oid}/dashboard` — 11 métriques agrégées
  - **Business Analytics** : completed/urgent WO, frequent_issues top 5, top_professionals top 5, average_property_health cross-property
  - **Multi-Location Map** : `GET /organizations/{oid}/map` — lat/lng + open_interventions + urgent + upcoming
  - **Business Documents** : 9 catégories (invoice/contract/report/certificate/guarantee/manual/inspection/safety/other) avec RBAC upload/delete
  - **Integrations stubs** : `GET /integrations/available` (10 items ERP/Accounting/FM/IoT/BMS all `coming_soon`) + `POST /organizations/{oid}/integrations` (owner-only, persiste config pour activation future)
  - **Meta** : `GET /enterprise/roles` (matrice complète), `/enterprise/account-types`
- **RBAC déclaratif** : chaque endpoint gate via `_require_org_permission(user_id, org_id, action)`. Non-membre → 403, permission manquante → 403 avec message clair.
- **Transition workflow** : `enterprise.WORK_ORDER_TRANSITIONS` fait office de graphe strict (draft→{pending_approval,cancelled}, pending_approval→{approved,rejected,cancelled}, approved→{in_progress,cancelled}, in_progress→{completed,cancelled}, completed/rejected/cancelled = terminal). Chaque transition écrit dans `history[]`.
- **Employee creates → pending_approval** automatiquement (workflow d'approbation). Manager/owner créent en draft (édition libre).
- **UI intacte** — 0 modif frontend. L'interface s'adaptera au prochain sprint UI (Business dashboard, work orders board, multi-location map).
- **Tests** : 60/60 pytest `test_enterprise_sprint.py` + 177/177 régression = **237/237 GREEN**.
- **Collections nouvelles** : `organizations`, `organization_members`, `work_orders`, `org_documents`, `org_integrations`. Champ `properties.organization_id` ajouté (nullable, backward-compat).

## Implemented (2026-07 — Sprint Growth & Retention)
### Ecosystem for long-term retention (25+ endpoints)
- **`services/growth.py`** : pro levels (5 tiers bronze/silver/gold/platinum/elite basés sur Trust + jobs, JAMAIS subscription), loyalty tiers (member/silver/gold/platinum/vip), health_label mapping, maintenance intervals par catégorie d'équipement, referral codes déterministes (uuid5 → AUX + 5 hex).
- **My Trusted Pros** : `GET/POST/DELETE /trusted-pros`. Idempotent.
- **Loyalty Program** :
  - `GET /loyalty/summary` (points, lifetime, tier, next_tier, rewards, earn_actions)
  - `GET /loyalty/ledger` (historique complet)
  - `POST /loyalty/redeem {reward_key}` (10€/25€ remise, priority_support, ai_boost, vip_status)
  - **Hooks automatiques** : booking_completed=+100 pts (client), review_posted=+25 pts, property_created=+50 pts, equipment_added=+10 pts, maintenance_completed=+75 pts, referral_converted=+500 pts (referrer) / +200 (referred).
- **Referral System** : `GET /referrals/mine` (code déterministe AUX+5hex, invitations, converted count) + `POST /referrals/redeem` (self-referral 400, dup 400, unknown code 404).
- **Pro Levels** : `GET /artisans/{aid}/level` (label + progress_pct + next_level). `GET /growth/levels` catalog.
- **Before/After Gallery** : `GET /artisans/{aid}/gallery`, `POST/DELETE /artisans/me/gallery` (max 6 photos before + 6 after, base64).
- **Property Health Score** : `GET /properties/{pid}/health` — pondéré (ok=100, attention/maintenance=60, replace=20). Empty → 100 excellent demo=true.
- **Maintenance Planner** : `GET /properties/{pid}/maintenance-plan` (schedule complet) + `POST .../generate-reminders` (idempotent, crée automatiquement des rappels dans `property_reminders`). 13 catégories couvertes.
- **Business Accounts** : `POST /business/setup`, `GET /business/mine`. 7 types (individual, company, property_manager, real_estate, hotel, restaurant, retail_chain). Architecture prête pour multi-property management.
- **Family Sharing** : `GET/POST/DELETE /properties/{pid}/members`. 5 rôles (owner/partner/child/tenant/manager) + permissions granulaires (can_book/can_view_documents/can_add_equipment). Status active si email connu, sinon invited.
- **Favourites** : `GET/POST/DELETE /favourites`. 3 kinds (pro/property/address). Idempotent.
- **Customer Analytics** : `GET /analytics/mine` — bookings/completed/total_spent/money_saved (heuristique 15%)/avg_repair_cost/avg_response_min/favourite_trade/trades_breakdown/property_count.
- **Tests** : 75/75 pytest `test_growth_sprint.py` + 102/102 régression = **177/177 GREEN**.
- **Collections nouvelles** : `trusted_pros`, `loyalty_summary`, `loyalty_ledger`, `loyalty_rewards`, `referrals`, `gallery_projects`, `business_accounts`, `property_members`, `favourites`.

## Implemented (2026-07 — Sprint AI Concierge / AURA)
### AURA — Conversational Home Assistant (flagship)
- **`services/concierge.py`** : moteur conversationnel multi-tour propulsé par GPT-4o + Whisper (via `emergentintegrations.LlmChat`). Prompt système strict → JSON. `initial_greeting()` déterministe (aucun appel LLM). `_augment_safety()` = filet de sécurité keyword-based indépendant du modèle (odeur gaz, électrocuté, inondation, effondrement → alerte forcée). `_sanitize()` garantit le schéma quoi qu'il arrive.
- **7 nouveaux endpoints** : `POST /concierge/start`, `POST /concierge/{sid}/message` (text + photos base64 + voice base64 auto-transcript Whisper), `POST /concierge/{sid}/finish` (force résumé final), `POST /concierge/{sid}/video` (placeholder architecture), `GET /concierge/sessions` (historique light), `GET /concierge/{sid}` (full), `DELETE /concierge/{sid}`.
- **Live diagnosis** à chaque tour : `{issue, confidence 0-100, urgency (faible|moyenne|elevee|urgence), duration_min/max_hours, price_min/max_eur, risks[]}`.
- **Questions dynamiques par métier** : plomberie/électricité/chauffage/serrurerie/toiture (adaptation via SYSTEM_PROMPT).
- **Safety alerts** : rendues avant tout, dedup via message, jamais rétrécies (le modèle peut en ajouter).
- **AI Summary** : à la fin, `summary = {problem, trade, trade_label, urgency, duration_hours, price_range_eur, materials, safety_advice, preparation_tips[], confidence}`. Enchaîne vers `/category/[slug]` (find pro → book → pay → track).
- **Frontend** : `/concierge/[id]` (chat conversationnel + live diagnosis banner + safety alerts + quick reply chips + voice via `useAudioRecorder` d'`expo-audio` + photos via `expo-image-picker` + video via `expo-document-picker` + input bar sticky safe-area) et `/concierge/index` (historique avec trade icons, status chips, urgence). Home button "J'ai un problème" route désormais vers `/concierge/[id]?id=new`.
- **Design intact** : dark + or champagne, Plus Jakarta Sans, existing UI kit. Aucune modif du système de tabs ou du design system.
- **Tests** : 24/24 pytest `test_concierge.py` + 78/78 régression (My Home + Trust + FinTech) = **102/102 GREEN**.

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
