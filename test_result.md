# Auxora — Sprint 8 Security Test Instructions

## User Problem Statement
User asked to implement Sprint 8: Security, Privacy, Authentication & Platform Integrity for Auxora (French-language mobile app). Must respond in FRENCH.

## What was implemented (Sprint 8)
1. **New service** `/app/backend/services/security.py`:
   - Enhanced session management with device fingerprinting (iOS/Android/macOS/Windows detection)
   - RBAC with 9 roles + `require_roles()` FastAPI dependency
   - Hash-chained immutable audit logs (SHA-256)
   - Rate limiting: 5 fails/email/15min + 30 distinct emails/IP for distributed brute-force
   - GDPR: data export + soft-delete/anonymization (30-day log retention)
   - MFA architecture stub (TOTP-ready, demo code 000000)
   - Biometrics registration stub
   - Security posture score

2. **Backend endpoints** added in `/app/backend/server.py`:
   - GET /api/security/overview
   - GET /api/security/sessions, DELETE /api/security/sessions/{id}, POST /revoke-others
   - POST /api/security/password/change
   - GET /api/security/audit (user's own logs), /audit/verify (admin), /audit/all (admin)
   - GET/POST /api/security/gdpr/consents
   - GET /api/security/gdpr/export
   - DELETE /api/security/gdpr/account
   - GET/POST/DELETE /api/security/mfa, /mfa/prepare, /mfa/verify
   - POST /api/security/biometrics/register
   - GET /api/security/roles
   - GET /api/security/admin/sessions (admin only)

3. **Frontend screens** in `/app/frontend/app/security/`:
   - `index.tsx` — Security Center (score + navigation)
   - `sessions.tsx` — Active sessions list + revoke
   - `audit.tsx` — Activity log
   - `mfa.tsx` — 2FA setup wizard
   - `password.tsx` — Change password form
   - `privacy.tsx` — GDPR consents + export + delete

4. **Enhanced auth flow**: audit logging on register/login/logout/google, rate-limit check on login

## Testing Status
- 13 new tests in `/app/backend/tests/test_security_sprint.py` — ALL PASSING
- Full test suite: 383 tests passing, 0 failures (verified)
- No regressions

## Test Credentials
See `/app/memory/test_credentials.md`

## What needs testing_agent validation
- Full end-to-end security flows via API and UI
- Confirm no regression to existing 383 tests
- Frontend flow: profile → Security Center → each sub-screen
