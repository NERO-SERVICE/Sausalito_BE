# PR Mapping (ADM Feature IDs)

## PR-A (Security Core)
- Feature IDs:
  - `ADM-SEC-001`
  - `ADM-SEC-003`
  - `ADM-SEC-004`
- Changes:
  - `User.admin_role` role model 추가
  - RBAC permission matrix + admin permission class
  - `AuditLog`, `IdempotencyRecord` 모델/유틸 추가
  - 개인정보 마스킹 + full-view 감사로그 적용
- Tests:
  - `test_ops_cannot_update_settlement`
  - `test_order_list_masks_pii_for_ops`
  - `test_order_list_full_pii_for_finance_and_logs_view`
  - `test_super_admin_can_change_admin_role_with_audit_log`

## PR-B (Order/Claim/Settlement Hardening)
- Feature IDs:
  - `ADM-ORD-002`
  - `ADM-SHIP-001`
  - `ADM-SHIP-002`
  - `ADM-CS-004`
  - `ADM-CS-005`
  - `ADM-SET-001`
  - `ADM-SET-002`
  - `ADM-SET-003`
  - `ADM-SET-007`
- Changes:
  - 주문/결제/배송 상태 전이 검증
  - 반품/환불 상태 전이 검증
  - 환불 실행 권한(`REFUND_EXECUTE`) 강제
  - 정산 상태 전이 검증
  - 상태 변경/환불/정산 API idempotency 처리
- Tests:
  - `test_finance_refund_is_idempotent`
  - `test_shipping_transition_is_validated`

## PR-C (Admin UI Minimal RBAC Alignment)
- Feature IDs:
  - `ADM-SEC-001`
  - `ADM-SEC-004`
- Changes:
  - 권한 기반 탭 노출/데이터 로드 분기
  - mutable API 호출 시 idempotency key 자동 부여
  - 권한 없는 액션 버튼/폼 실행 차단
  - 회원 표에 관리자 역할 표시
- Validation:
  - `npm run build` (`sausalito_admin`)
