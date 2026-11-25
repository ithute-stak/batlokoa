-- Candidate only. Apply after branch location schema in a reviewed migration.
-- Runtime privileges and tenant isolation require separate review.
ALTER TABLE staff_branch_location_history
    ADD CONSTRAINT staff_branch_location_revision_scope
    UNIQUE (company_id, branch_id, revision_id);

CREATE TABLE staff_attendance_sessions (
    session_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    clocked_in_at timestamptz NOT NULL,
    clocked_out_at timestamptz,
    UNIQUE (session_id, company_id, employee_id, branch_id),
    CHECK (clocked_out_at IS NULL OR clocked_out_at >= clocked_in_at)
);

CREATE UNIQUE INDEX staff_attendance_one_open_session
    ON staff_attendance_sessions (company_id, employee_id)
    WHERE clocked_out_at IS NULL;

CREATE TABLE staff_attendance_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id bigint NOT NULL,
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('clock_in', 'clock_out')),
    recorded_at timestamptz NOT NULL,
    location_revision bigint NOT NULL,
    location_state text NOT NULL CHECK (location_state = 'verified_inside'),
    UNIQUE (session_id, action),
    FOREIGN KEY (session_id, company_id, employee_id, branch_id)
        REFERENCES staff_attendance_sessions (session_id, company_id, employee_id, branch_id),
    FOREIGN KEY (company_id, branch_id, location_revision)
        REFERENCES staff_branch_location_history (company_id, branch_id, revision_id)
);

CREATE INDEX staff_attendance_event_history
    ON staff_attendance_events (company_id, employee_id, recorded_at DESC);

REVOKE ALL ON staff_attendance_sessions, staff_attendance_events FROM PUBLIC;
-- Session creation/closure and audit insertion must share one transaction.
-- Events must be insert/select only for non-owner runtime roles.
-- Rejected attempts and monitoring alerts belong in separate audit records.
