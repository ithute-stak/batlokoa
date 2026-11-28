"""Explicitly released single-company attendance worker composition.

Run as a dedicated process, not an in-process web-server background thread.
Deployment must supply a restricted database role, migrations and a certified
relay receiver. No network/database work is performed when disabled.
"""
import os
import time
import signal
import logging
from datetime import datetime
from uuid import UUID

import psycopg

from .staff_morning_loanhub_directory import LoanHubMorningDirectory
from .staff_morning_roster_source import DatabaseMorningRosterSource
from .staff_morning_reminder_queue import MorningReminderQueue
from .staff_morning_reminder_scheduler import MorningReminderScheduler
from .staff_morning_reminder_worker import MorningReminderWorker
from .staff_morning_reminder_relay import MorningReminderRelayProvider
from .staff_attendance_notification_queue import AttendanceDeliveryQueue
from .staff_attendance_dispatch_worker import AttendanceDispatchWorker
from .staff_attendance_relay_provider import AttendanceRelayProvider
from .staff_access_notification_queue import AccessDeliveryQueue
from .staff_access_dispatch_worker import AccessDispatchWorker
from .staff_access_relay_provider import AccessRelayProvider


def build_workers(env):
    if env.get("STAFF_ATTENDANCE_WORKER_ENABLED") != "true":
        return None
    company = UUID(env["STAFF_ATTENDANCE_WORKER_COMPANY_ID"])
    dsn = env["STAFF_ATTENDANCE_WORKER_DATABASE_URL"]
    release = datetime.fromisoformat(env["STAFF_ATTENDANCE_WORKER_RELEASE_AT"])
    if release.utcoffset() is None or not dsn:
        raise ValueError("Restricted database and aware release cutoff required")
    relay_token = env["STAFF_ATTENDANCE_RELAY_TOKEN"]
    directory_token = env["STAFF_ATTENDANCE_DIRECTORY_TOKEN"]
    if (len(relay_token) < 32 or len(directory_token) < 32 or relay_token == directory_token):
        raise ValueError("Distinct dedicated service credentials required")
    def connect():
        return psycopg.connect(dsn, connect_timeout=5,
                               options="-c statement_timeout=10000 -c lock_timeout=5000")
    relay = {"origin": env["STAFF_ATTENDANCE_RELAY_ORIGIN"],
             "company_id": company, "token": relay_token}
    directory = LoanHubMorningDirectory(origin=env["STAFF_ATTENDANCE_LOANHUB_ORIGIN"],
                    company_id=company, token=directory_token)
    source = DatabaseMorningRosterSource(connect, directory, company_id=company)
    queue = MorningReminderQueue(connect, company_id=company)
    return (
        MorningReminderScheduler(queue, source, company_id=company, enabled=True),
        MorningReminderWorker(queue, source, MorningReminderRelayProvider(**relay), enabled=True),
        AttendanceDispatchWorker(AttendanceDeliveryQueue(connect, company_id=company,
            release_at=release), AttendanceRelayProvider(**relay), enabled=True),
        AccessDispatchWorker(AccessDeliveryQueue(connect, company_id=company,
            release_at=release), AccessRelayProvider(**relay), enabled=True),
    )


def run_cycle(workers, *, stopping=lambda: False):
    """Isolate stage failures and expose only aggregate operational status."""
    logger = logging.getLogger(__name__)
    for index, worker in enumerate(workers):
        if stopping():
            break
        try:
            report = worker.tick() if index == 0 else worker.run_once(limit=5)
            if getattr(report, "unavailable", False):
                logger.warning("Attendance worker stage %d unavailable", index)
            else:
                logger.info("Attendance worker stage %d completed: %s", index, report)
        except Exception:
            logger.error("Attendance worker stage %d failed", index)


def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    try:
        workers = build_workers(os.environ)
    except Exception:
        logger.error("Attendance worker configuration invalid")
        return 2
    if workers is None:
        logger.info("Attendance worker disabled")
        return 0
    stop = False
    def request_stop(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop:
        run_cycle(workers, stopping=lambda: stop)
        deadline = time.monotonic() + 15
        while not stop and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0, deadline-time.monotonic())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
