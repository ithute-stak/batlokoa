-- Durable in-app notification inbox. Recipient authorization is rechecked on read.
CREATE TABLE staff_attendance_notification_inbox (
    company_id uuid NOT NULL,
    recipient_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    employee_id uuid NOT NULL,
    event_type text NOT NULL CHECK (event_type IN (
        'morning_reminder', 'reported_outside_perimeter', 'reported_inside_perimeter',
        'reported_login_outside', 'staff_logged_out')),
    observed_at timestamptz NOT NULL,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    read_at timestamptz,
    PRIMARY KEY (company_id, recipient_id, idempotency_key),
    CHECK ((event_type = 'morning_reminder') = (expires_at IS NOT NULL)),
    CHECK (event_type <> 'morning_reminder' OR recipient_id = employee_id),
    CHECK (expires_at IS NULL OR expires_at > observed_at),
    CHECK (read_at IS NULL OR read_at >= created_at)
);
CREATE INDEX staff_attendance_inbox_recipient
    ON staff_attendance_notification_inbox (company_id, recipient_id, created_at DESC, idempotency_key);
REVOKE ALL ON staff_attendance_notification_inbox FROM PUBLIC;

-- No GPS coordinates or contact details. This inbox is not proof of human
-- receipt. The receiver must derive recipients from verified current membership,
-- never from the sender payload, and validate original event/queue records.
-- Apply via reviewed migrations and narrowly scoped runtime grants.
