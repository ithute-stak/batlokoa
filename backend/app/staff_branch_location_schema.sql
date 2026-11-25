-- Candidate schema: apply only through a reviewed privileged migration.
-- No runtime grants or production activation are included.
-- Each registration is an immutable historical revision; latest revision is current.
CREATE TABLE staff_branch_location_history (
    revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id uuid NOT NULL,
    branch_id uuid NOT NULL,
    latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy_m double precision NOT NULL CHECK (accuracy_m > 0 AND accuracy_m <= 5),
    radius_m double precision NOT NULL DEFAULT 10 CHECK (radius_m = 10),
    registered_by uuid NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX staff_branch_location_history_lookup
    ON staff_branch_location_history (company_id, branch_id, revision_id DESC);
-- Runtime writer must receive INSERT/SELECT only, never UPDATE/DELETE/TRUNCATE,
-- and must not own this table. Tenant and branch authorization must precede
-- every operation; this schema alone does not enforce tenant isolation.
REVOKE ALL ON staff_branch_location_history FROM PUBLIC;
