"""Candidate attendance delivery queue. No scheduler or provider activation.

A worker is explicitly bound to one company and a release cutoff. The provider
must independently resolve authorized recipients and support idempotency.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class DeliveryClaim:
    alert_id: int
    company_id: UUID
    employee_id: UUID
    branch_id: UUID
    event_type: str
    observed_at: datetime
    lease_token: UUID
    attempts: int

    @property
    def idempotency_key(self):
        return f"batlokoa:attendance:{self.company_id}:{self.alert_id}"


class AttendanceDeliveryQueue:
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
                cur.execute("""INSERT INTO staff_attendance_notification_delivery (alert_id)
                    SELECT a.alert_id FROM staff_attendance_monitor_outbox a
                    WHERE a.company_id=%s AND a.observed_at >= %s
                      AND a.observed_at <= clock_timestamp()
                      AND a.delivered_at IS NULL
                      AND NOT EXISTS (SELECT 1 FROM staff_attendance_notification_delivery d
                                      WHERE d.alert_id=a.alert_id)
                    ORDER BY a.alert_id LIMIT %s
                    ON CONFLICT (alert_id) DO NOTHING""",
                    (self._company_id, self._release_at, limit))
                return cur.rowcount

    def claim(self):
        token = uuid4()
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Expired final attempts are terminal, not silently retried.
                cur.execute("""UPDATE staff_attendance_notification_delivery d
                    SET state='dead', lease_token=NULL, lease_until=NULL,
                        last_error_code='lease_expired'
                    FROM staff_attendance_monitor_outbox a
                    WHERE a.alert_id=d.alert_id AND a.company_id=%s
                      AND a.observed_at >= %s AND d.state='leased'
                      AND d.lease_until <= clock_timestamp() AND d.attempts=10""",
                    (self._company_id, self._release_at))
                cur.execute("""WITH candidate AS (
                    SELECT d.alert_id FROM staff_attendance_notification_delivery d
                    JOIN staff_attendance_monitor_outbox a ON a.alert_id=d.alert_id
                    WHERE a.company_id=%s AND a.observed_at >= %s
                      AND a.delivered_at IS NULL AND d.attempts < 10
                      AND ((d.state='pending' AND d.available_at <= clock_timestamp())
                        OR (d.state='leased' AND d.lease_until <= clock_timestamp()))
                    ORDER BY d.available_at, d.alert_id
                    LIMIT 1 FOR UPDATE OF d SKIP LOCKED
                )
                UPDATE staff_attendance_notification_delivery d
                SET state='leased', attempts=d.attempts+1, lease_token=%s,
                    lease_until=clock_timestamp()+interval '120 seconds'
                FROM candidate c, staff_attendance_monitor_outbox a
                WHERE d.alert_id=c.alert_id AND a.alert_id=d.alert_id
                RETURNING d.alert_id, a.company_id, a.employee_id, a.branch_id,
                    a.event_type, a.observed_at, d.lease_token, d.attempts""",
                    (self._company_id, self._release_at, token))
                row = cur.fetchone()
                return DeliveryClaim(*row) if row else None

    def _scope(self, claim):
        if not isinstance(claim, DeliveryClaim) or claim.company_id != self._company_id:
            raise ValueError("Claim outside worker scope")
        return claim.alert_id, claim.lease_token, self._company_id, self._release_at

    def acknowledge(self, claim):
        """Call only after a provider confirms acceptance of the idempotent send."""
        scope = self._scope(claim)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_attendance_notification_delivery d
                    SET state='delivered', delivered_at=clock_timestamp(),
                        lease_token=NULL, lease_until=NULL, last_error_code=NULL
                    FROM staff_attendance_monitor_outbox a
                    WHERE d.alert_id=%s AND d.lease_token=%s AND a.alert_id=d.alert_id
                      AND a.company_id=%s AND a.observed_at >= %s
                      AND d.state='leased' AND d.lease_until > clock_timestamp()
                    RETURNING d.delivered_at""", scope)
                row = cur.fetchone()
                if row is None:
                    return False
                cur.execute("""UPDATE staff_attendance_monitor_outbox
                    SET delivered_at=%s WHERE alert_id=%s AND company_id=%s
                    AND delivered_at IS NULL""", (row[0], claim.alert_id, self._company_id))
                if cur.rowcount != 1:
                    raise RuntimeError("Outbox acknowledgement conflict")
                return True

    def fail(self, claim, *, code, permanent=False):
        if code not in {"provider_unavailable", "recipient_unavailable", "provider_rejected"}:
            raise ValueError("Invalid sanitized failure code")
        if type(permanent) is not bool:
            raise ValueError("Invalid permanent failure flag")
        scope = self._scope(claim)
        with self._connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("""UPDATE staff_attendance_notification_delivery d
                    SET state=CASE WHEN %s OR d.attempts >= 10 THEN 'dead' ELSE 'pending' END,
                        available_at=clock_timestamp()+
                            LEAST(3600, 30 * power(2, d.attempts-1)) * interval '1 second',
                        lease_token=NULL, lease_until=NULL, last_error_code=%s
                    FROM staff_attendance_monitor_outbox a
                    WHERE d.alert_id=%s AND d.lease_token=%s AND a.alert_id=d.alert_id
                      AND a.company_id=%s AND a.observed_at >= %s
                      AND d.state='leased' AND d.lease_until > clock_timestamp()""",
                    (permanent, code, *scope))
                return cur.rowcount == 1
