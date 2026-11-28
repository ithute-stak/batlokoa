"""Candidate access-event delivery queue. No scheduler or provider activation.

A worker is explicitly bound to one company and a release cutoff. The provider
must independently resolve authorized recipients and support idempotency.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AccessDeliveryClaim:
    event_id: UUID
    company_id: UUID
    employee_id: UUID
    branch_id: UUID | None
    event_type: str
    observed_at: datetime
    lease_token: UUID
    attempts: int

    @property
    def idempotency_key(self):
        return f"batlokoa:access:{self.company_id}:{self.event_id}"


class AccessDeliveryQueue:
    def __init__(self, connect, *, company_id, release_at):
        if not isinstance(company_id, UUID):
            raise ValueError("Explicit company required")
        if not isinstance(release_at, datetime) or release_at.utcoffset() is None:
            raise ValueError("Explicit timezone-aware release cutoff required")
        self._connect = connect
        self._company_id = company_id
        self._release_at = release_at

    def enqueue(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid batch size")
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""INSERT INTO staff_access_notification_delivery (event_id)
                    SELECT a.event_id FROM staff_attendance_access_events a
                    WHERE a.company_id=%s AND a.observed_at >= %s
                      AND a.observed_at <= clock_timestamp()
                      AND NOT EXISTS (SELECT 1 FROM staff_access_notification_delivery d
                                      WHERE d.event_id=a.event_id)
                    ORDER BY a.observed_at, a.event_id LIMIT %s
                    ON CONFLICT (event_id) DO NOTHING""",
                    (self._company_id, self._release_at, limit))
                return cur.rowcount

    def claim(self):
        token = uuid4()
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Expired final attempts are terminal, not silently retried.
                cur.execute("""UPDATE staff_access_notification_delivery d
                    SET state='dead', lease_token=NULL, lease_until=NULL,
                        last_error_code='lease_expired'
                    FROM staff_attendance_access_events a
                    WHERE a.event_id=d.event_id AND a.company_id=%s
                      AND a.observed_at >= %s AND d.state='leased'
                      AND d.lease_until <= clock_timestamp() AND d.attempts=10""",
                    (self._company_id, self._release_at))
                cur.execute("""WITH candidate AS (
                    SELECT d.event_id FROM staff_access_notification_delivery d
                    JOIN staff_attendance_access_events a ON a.event_id=d.event_id
                    WHERE a.company_id=%s AND a.observed_at >= %s
                      AND d.attempts < 10
                      AND ((d.state='pending' AND d.available_at <= clock_timestamp())
                        OR (d.state='leased' AND d.lease_until <= clock_timestamp()))
                    ORDER BY d.available_at, d.event_id
                    LIMIT 1 FOR UPDATE OF d SKIP LOCKED
                )
                UPDATE staff_access_notification_delivery d
                SET state='leased', attempts=d.attempts+1, lease_token=%s,
                    lease_until=clock_timestamp()+interval '120 seconds'
                FROM candidate c, staff_attendance_access_events a
                WHERE d.event_id=c.event_id AND a.event_id=d.event_id
                RETURNING d.event_id, a.company_id, a.employee_id, a.branch_id,
                    a.event_type, a.observed_at, d.lease_token, d.attempts""",
                    (self._company_id, self._release_at, token))
                row = cur.fetchone()
                return AccessDeliveryClaim(*row) if row else None

    def _scope(self, claim):
        if not isinstance(claim, AccessDeliveryClaim) or claim.company_id != self._company_id:
            raise ValueError("Claim outside worker scope")
        return claim.event_id, claim.lease_token, self._company_id, self._release_at

    def acknowledge(self, claim):
        """Call only after a provider confirms acceptance of the idempotent send."""
        scope = self._scope(claim)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_access_notification_delivery d
                    SET state='delivered', delivered_at=clock_timestamp(),
                        lease_token=NULL, lease_until=NULL, last_error_code=NULL
                    FROM staff_attendance_access_events a
                    WHERE d.event_id=%s AND d.lease_token=%s AND a.event_id=d.event_id
                      AND a.company_id=%s AND a.observed_at >= %s
                      AND d.state='leased' AND d.lease_until > clock_timestamp()
                    RETURNING d.delivered_at""", scope)
                return cur.fetchone() is not None

    def fail(self, claim, *, code, permanent=False):
        if code not in {"provider_unavailable", "recipient_unavailable", "provider_rejected"}:
            raise ValueError("Invalid sanitized failure code")
        if type(permanent) is not bool:
            raise ValueError("Invalid permanent failure flag")
        scope = self._scope(claim)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_access_notification_delivery d
                    SET state=CASE WHEN %s OR d.attempts >= 10 THEN 'dead' ELSE 'pending' END,
                        available_at=clock_timestamp()+
                            LEAST(3600, 30 * power(2, d.attempts-1)) * interval '1 second',
                        lease_token=NULL, lease_until=NULL, last_error_code=%s
                    FROM staff_attendance_access_events a
                    WHERE d.event_id=%s AND d.lease_token=%s AND a.event_id=d.event_id
                      AND a.company_id=%s AND a.observed_at >= %s
                      AND d.state='leased' AND d.lease_until > clock_timestamp()""",
                    (permanent, code, *scope))
                return cur.rowcount == 1
