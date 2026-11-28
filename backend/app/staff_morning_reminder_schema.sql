-- Candidate migration: morning reminder delivery ledger.
-- Apply only after migration and runtime privilege review.
-- A verified current work roster is required before enqueue and delivery.
-- Never infer eligibility from a missing roster or unavailable attendance data.
CREATE TABLE staff_morning_reminder_delivery (
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    work_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'leased', 'delivered', 'dead', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_token uuid,
    lease_until timestamptz,
    delivered_at timestamptz,
    last_error_code text CHECK (last_error_code IN
        ('provider_unavailable', 'recipient_unavailable', 'provider_rejected',
         'lease_expired', 'window_closed', 'no_longer_eligible', 'eligibility_unverified')),
    PRIMARY KEY (company_id, employee_id, work_date),
    CHECK ((state = 'leased') = (lease_token IS NOT NULL)),
    CHECK ((state = 'leased') = (lease_until IS NOT NULL)),
    CHECK ((state = 'delivered') = (delivered_at IS NOT NULL)),
    CHECK (state <> 'leased' OR attempts > 0),
    CHECK (state <> 'delivered' OR attempts > 0),
    CHECK (work_date = (created_at AT TIME ZONE 'Africa/Maseru')::date),
    CHECK ((created_at AT TIME ZONE 'Africa/Maseru')::time >= TIME '07:00'),
    CHECK ((created_at AT TIME ZONE 'Africa/Maseru')::time < TIME '07:15')
);

CREATE INDEX staff_morning_reminder_pending
    ON staff_morning_reminder_delivery (company_id, work_date, available_at, employee_id)
    WHERE state = 'pending';

CREATE INDEX staff_morning_reminder_leased
    ON staff_morning_reminder_delivery (company_id, work_date, lease_until, employee_id)
    WHERE state = 'leased';

REVOKE ALL ON staff_morning_reminder_delivery FROM PUBLIC;

-- All queue operations must constrain the explicitly configured company.
-- Before send, revalidate current active employment, schedule and attendance.
-- Pending and expired leased rows must not be sent after the morning window.
-- Use the stable daily key at the receiving provider for retry deduplication;
-- database uniqueness alone does not guarantee exactly-once external delivery.
-- Do not delete completed daily rows during the applicable retry window.
-- No phone numbers, message contents, or coordinates are stored in this ledger.
