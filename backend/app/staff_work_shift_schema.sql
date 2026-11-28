-- Candidate migration: apply separately after the existing roster schema.
-- No inferred defaults for legacy working days.
CREATE TABLE staff_work_shifts (
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    work_date date NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    grace_minutes integer NOT NULL CHECK (grace_minutes BETWEEN 0 AND 120),
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (company_id, employee_id, work_date),
    FOREIGN KEY (company_id, employee_id, work_date)
        REFERENCES staff_morning_work_roster (company_id, employee_id, work_date),
    CHECK (ends_at > starts_at AND ends_at <= starts_at + interval '24 hours'),
    CHECK ((starts_at AT TIME ZONE 'Africa/Maseru')::date = work_date),
    CHECK (ends_at > starts_at + grace_minutes * interval '1 minute')
);
REVOKE ALL ON staff_work_shifts FROM PUBLIC;
-- Explicit reviewed runtime grants and owner authorization required.
-- A shift on a non-working roster day must not be used for classification.
