-- Candidate access-event ledger, independent of clock-in sessions.
-- 
-- An outside-office login may occur before a clock-in exists. Use a separate
-- source table rather than fabricating an attendance session. The login boundary
-- must supply verified identity and a server-generated opaque event UUID.
-- No session cookie, access token, password, or raw coordinates are stored.
CREATE TABLE staff_attendance_access_events (
    event_id uuid PRIMARY KEY,
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    branch_id uuid,
    event_type text NOT NULL CHECK (event_type IN ('reported_login_outside', 'staff_logged_out')),
    location_revision bigint,
    observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (company_id, branch_id, location_revision)
        REFERENCES staff_branch_location_history (company_id, branch_id, revision_id),
    CHECK ((event_type = 'reported_login_outside') = (location_revision IS NOT NULL)),
    CHECK (location_revision IS NULL OR branch_id IS NOT NULL)
);
CREATE INDEX staff_attendance_access_company_time
    ON staff_attendance_access_events (company_id, observed_at, event_id);
REVOKE ALL ON staff_attendance_access_events FROM PUBLIC;
-- Separate inbox and dispatch integration and runtime grants are required.
