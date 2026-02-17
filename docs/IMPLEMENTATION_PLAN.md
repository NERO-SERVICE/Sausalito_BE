# Sausalito Admin P0 Implementation Plan

## Assumptions (Conservative)
- Undefined policy values default to secure behavior (deny-by-default, least privilege).
- Full PII view is restricted to `SUPER_ADMIN` and `FINANCE`.
- All state mutation APIs accept and process `idempotency_key`.
- Status transition follows server-side rule tables; invalid transitions are rejected with `400`.
- Existing legacy order/payment/shipping states are retained for backward compatibility, while transition constraints are enforced.
- Refund execution is limited to roles with `REFUND_EXECUTE` permission.

## Architecture Summary
- Backend: Django + DRF APIView-based admin APIs.
- AuthN: JWT (`/auth/login`, `/auth/refresh`, `/auth/logout`).
- AuthZ: New RBAC matrix based on `User.admin_role` + permission constants.
- Audit: New `AuditLog` table + standardized logging utility.
- Idempotency: New `IdempotencyRecord` table + replay handling utility.
- PII: Role-based masking utility + full-view access audit.

## DB Changes
- `accounts.User.admin_role` (enum)
- `accounts.AuditLog`
- `accounts.IdempotencyRecord`
- Migration: `accounts.0004_user_admin_role_idempotencyrecord_auditlog`

## API Changes (P0 Core)
- RBAC enforced server-side on all `/admin/*` APIs (`AdminRBACPermission`).
- New admin endpoint:
  - `GET /api/v1/admin/audit-logs`
- Idempotency key support added to mutable admin APIs:
  - order update, inquiry update, review visibility/delete, return create/update/delete, settlement generate/update/delete, user update/delete
- Transition validation added:
  - order/payment/shipping transitions
  - return/refund transitions
  - settlement status transitions
- Refund execution permission guard:
  - return status -> `REFUNDING` / `REFUNDED` requires `REFUND_EXECUTE`
- PII masking + full-view audit:
  - orders / users / inquiries / returns / settlements responses

## Admin UI Changes (Minimal, UI-preserving)
- Permission-aware data loading (prevents full-page failure for non-super roles).
- Tab visibility controlled by backend-provided `permissions`.
- Action guards for mutation buttons/forms.
- Auto-generated `idempotency_key` for state-changing requests.
- Member table now shows `adminRole`.

## Feature ID Mapping (Primary)
- `ADM-SEC-001`: role model + RBAC matrix + permission enforcement
- `ADM-SEC-003`: audit log model, utilities, audit log API
- `ADM-SEC-004`: PII masking + full-view access logging
- `ADM-ORD-002`, `ADM-SHIP-001`, `ADM-SHIP-002`: order/shipping transition validation + audited mutation
- `ADM-CS-004`, `ADM-CS-005`: refund execution permission + idempotent return/refund processing
- `ADM-SET-001`, `ADM-SET-002`, `ADM-SET-003`, `ADM-SET-007`: settlement transition/idempotency/audit hardening

## Priority / Timeline
- `P0` (implemented now)
  - RBAC, audit, idempotency, transition checks, PII masking, admin UI permission guards, core regression tests
- `P1` (next)
  - richer OpenAPI annotations for all APIViews, claim reason-code policy, download/export controls, staff workflow UX
- `P2` (later)
  - external systems deep integration (PG reconciliation automation, courier/OMS advanced sync), advanced risk/compliance workflows
