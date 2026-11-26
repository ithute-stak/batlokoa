-- Candidate company-scoped explicit daily work roster.
-- Missing rows mean unknown schedule, never an assumed working day.
-- Populate only through a verified owner-authorized scheduling service.
CREATE TABLE staff_morning_work_roster (
    company_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    work_date date NOT NULL,
    scheduled_to_work boolean NOT NULL,
    recorded_by uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (company_id, employee_id, work_date)
);

CREATE INDEX staff_morning_work_roster_daily
    ON staff_morning_work_roster (company_id, work_date, employee_id)
    WHERE scheduled_to_work IS TRUE;

REVOKE ALL ON staff_morning_work_roster FROM PUBLIC;

-- A roster row is not evidence of current employment or authorization.
-- Verify current active membership independently before enqueue and dispatch.
-- Runtime grants must separate owner-authorized writes and reminder reads.
-- No personal contact details or location samples belong in this table.
-- Review retention and migration privileges before release.
