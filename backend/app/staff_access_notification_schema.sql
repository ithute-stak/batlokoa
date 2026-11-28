-- Candidate migration, after staff_attendance_access_events_schema.sql.
-- External dispatch is opt-in. No recipients, credentials or coordinates are stored here.
-- A delivery adapter must resolve an authorized recipient for this company at send time.
CREATE TABLE staff_access_notification_delivery (
    event_id uuid PRIMARY KEY REFERENCES staff_attendance_access_events(event_id),
    state text NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'leased', 'delivered', 'dead')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
    available_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_token uuid,
    lease_until timestamptz,
    delivered_at timestamptz,
    last_error_code text CHECK (last_error_code IN
        ('provider_unavailable', 'recipient_unavailable', 'provider_rejected', 'lease_expired')),
    CHECK ((state = 'leased') = (lease_token IS NOT NULL)),
    CHECK ((state = 'leased') = (lease_until IS NOT NULL)),
    CHECK ((state = 'delivered') = (delivered_at IS NOT NULL)),
    CHECK (state <> 'leased' OR attempts > 0),
    CHECK (state <> 'delivered' OR attempts > 0)
);

CREATE INDEX staff_access_notification_available
    ON staff_access_notification_delivery (available_at, event_id)
    WHERE state = 'pending';
CREATE INDEX staff_access_notification_expired_lease
    ON staff_access_notification_delivery (lease_until, event_id)
    WHERE state = 'leased';

REVOKE ALL ON staff_access_notification_delivery FROM PUBLIC;

-- The worker will enqueue only events for an explicitly configured company,
-- with a release-time lower bound; no automatic historical replay.
-- Claim, retry and acknowledgement operations must join the source access event
-- and constrain company_id, with lease-token fencing and stable provider
-- idempotency keys. Never mark delivery from an inbox read.
-- Separate worker grants and retention policy are required before activation.
