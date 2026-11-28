-- Candidate migration: apply only after staff_attendance_schema.sql.
-- No raw GPS coordinates are retained by the monitoring state or alert outbox.
CREATE TABLE staff_attendance_monitor_state (
    session_id bigint PRIMARY KEY,
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    location_revision bigint NOT NULL,
    last_observed_at timestamptz NOT NULL,
    last_captured_at timestamptz NOT NULL,
    last_confirmed text NOT NULL CHECK (last_confirmed IN ('verified_inside', 'verified_outside')),
    candidate_since timestamptz,
    candidate text CHECK (candidate IN ('verified_inside', 'verified_outside')),
    transition_sequence bigint NOT NULL DEFAULT 0 CHECK (transition_sequence >= 0),
    FOREIGN KEY (session_id, company_id, employee_id, branch_id)
        REFERENCES staff_attendance_sessions (session_id, company_id, employee_id, branch_id),
    FOREIGN KEY (company_id, branch_id, location_revision)
        REFERENCES staff_branch_location_history (company_id, branch_id, revision_id),
    CHECK ((candidate IS NULL) = (candidate_since IS NULL)),
    CHECK (candidate IS NULL OR candidate <> last_confirmed),
    CHECK (candidate_since IS NULL OR candidate_since <= last_observed_at)
);

-- Insert atomically with the monitoring transition under the same session lock.
-- Delivery is separate and must use an idempotent notification adapter.
CREATE TABLE staff_attendance_monitor_outbox (
    alert_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id bigint NOT NULL,
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    location_revision bigint NOT NULL,
    transition_sequence bigint NOT NULL CHECK (transition_sequence > 0),
    event_type text NOT NULL CHECK (event_type IN
        ('reported_outside_perimeter', 'reported_inside_perimeter')),
    observed_at timestamptz NOT NULL,
    delivered_at timestamptz,
    UNIQUE (session_id, transition_sequence),
    FOREIGN KEY (session_id, company_id, employee_id, branch_id)
        REFERENCES staff_attendance_sessions (session_id, company_id, employee_id, branch_id),
    FOREIGN KEY (company_id, branch_id, location_revision)
        REFERENCES staff_branch_location_history (company_id, branch_id, revision_id),
    CHECK (delivered_at IS NULL OR delivered_at >= observed_at)
);

CREATE INDEX staff_monitor_pending_alerts
    ON staff_attendance_monitor_outbox (company_id, alert_id)
    WHERE delivered_at IS NULL;

REVOKE ALL ON staff_attendance_monitor_state, staff_attendance_monitor_outbox FROM PUBLIC;
-- Runtime grants, row-level tenant protection, retention and delivery worker
-- permissions require separate review before any deployment.
