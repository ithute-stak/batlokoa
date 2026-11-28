-- Staging-only grants. Run as schema owner after fresh installation.
-- Operator must provision distinct non-owner, non-superuser LOGIN roles
-- with no inherited elevated privileges before running this transaction.
BEGIN;
GRANT USAGE ON SCHEMA public TO batlokoa_attendance_gateway, batlokoa_attendance_worker;
GRANT SELECT, INSERT ON staff_branch_location_history TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_attendance_sessions TO batlokoa_attendance_gateway;
GRANT UPDATE (clocked_out_at) ON staff_attendance_sessions TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_attendance_events TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_attendance_monitor_state TO batlokoa_attendance_gateway;
GRANT UPDATE (location_revision, last_observed_at, last_captured_at, last_confirmed,
    candidate_since, candidate, transition_sequence)
    ON staff_attendance_monitor_state TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_attendance_monitor_outbox, staff_attendance_access_events
    TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_morning_work_roster TO batlokoa_attendance_gateway;
GRANT UPDATE (scheduled_to_work, recorded_by, recorded_at)
    ON staff_morning_work_roster TO batlokoa_attendance_gateway;
GRANT SELECT ON staff_attendance_notification_delivery, staff_access_notification_delivery,
    staff_morning_reminder_delivery TO batlokoa_attendance_gateway;
GRANT SELECT, INSERT ON staff_attendance_notification_inbox TO batlokoa_attendance_gateway;

GRANT SELECT ON staff_attendance_sessions, staff_morning_work_roster,
    staff_attendance_monitor_outbox, staff_attendance_access_events
    TO batlokoa_attendance_worker;
GRANT UPDATE (delivered_at) ON staff_attendance_monitor_outbox TO batlokoa_attendance_worker;
GRANT SELECT, INSERT ON staff_attendance_notification_delivery,
    staff_access_notification_delivery, staff_morning_reminder_delivery
    TO batlokoa_attendance_worker;
GRANT UPDATE (state, attempts, available_at, lease_token, lease_until,
    delivered_at, last_error_code) ON staff_attendance_notification_delivery,
    staff_access_notification_delivery, staff_morning_reminder_delivery
    TO batlokoa_attendance_worker;

-- No DELETE, TRUNCATE, DDL, blanket sequence grants or grants to PUBLIC.
-- Company scoping remains application-enforced; these grants are not RLS.
-- Validate effective privileges (including inherited grants) and exercise
-- each operation under its real role before authorizing any release.
COMMIT;
