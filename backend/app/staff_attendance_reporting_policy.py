"""Pure reporting policy. Never infer absence from missing telemetry."""
from datetime import datetime, timedelta


def classify_attendance(*, scheduled_to_work, shift_start, shift_end,
                        first_clock_in, as_of, records_complete,
                        grace_minutes=0):
    """Classify a verified daily record against an explicitly configured shift.

    A missing clock-in is not proof of physical absence. The caller must
    supply complete authoritative records and the actual employee schedule.
    """
    if type(grace_minutes) is not int or not 0 <= grace_minutes <= 120:
        raise ValueError("Invalid grace period")
    for value in (shift_start, shift_end, first_clock_in, as_of):
        if value is not None and (
                not isinstance(value, datetime) or value.utcoffset() is None):
            raise ValueError("Timezone-aware timestamps required")
    if as_of is None:
        raise ValueError("Report cutoff required")
    if scheduled_to_work is False:
        return "not_scheduled"
    if (scheduled_to_work is not True or records_complete is not True
            or shift_start is None or shift_end is None):
        return "unknown"
    if shift_end <= shift_start:
        raise ValueError("Invalid shift interval")
    if first_clock_in is not None:
        if first_clock_in > as_of or first_clock_in >= shift_end:
            raise ValueError("Clock-in outside report interval")
        return ("late" if first_clock_in > shift_start + timedelta(minutes=grace_minutes)
                else "on_time")
    if as_of < shift_end:
        return "pending_clock_in" if as_of >= shift_start else "not_started"
    return "no_recorded_clock_in"
