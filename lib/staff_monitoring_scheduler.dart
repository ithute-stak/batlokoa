import 'dart:async';

import 'staff_gateway.dart';
import 'staff_location_capture.dart';

/// Foreground-only scheduler. The UI must disclose monitoring and explicitly
/// start it, then stop it on sign-out, suspension and disposal.
class StaffMonitoringScheduler {
  final StaffAttendanceGateway attendance;
  final StaffMonitoringGateway monitoring;
  final Future<StaffLocationCapture> Function() capture;
  final void Function(StaffMonitorReceipt?) onReading;
  final Duration interval;

  Timer? _timer;
  bool _enabled = false;
  bool _inFlight = false;
  int _generation = 0;

  StaffMonitoringScheduler({
    required this.attendance,
    required this.monitoring,
    required this.onReading,
    this.capture = captureStaffLocation,
    this.interval = const Duration(seconds: 30),
  }) {
    if (interval < const Duration(seconds: 15) ||
        interval > const Duration(seconds: 120)) {
      throw ArgumentError('Monitoring interval outside confirmation window');
    }
  }

  bool get enabled => _enabled;

  void start() {
    if (_enabled) return;
    _enabled = true;
    _generation++;
    _timer = Timer.periodic(interval, (_) => unawaited(_tick()));
    unawaited(_tick());
  }

  void stop() {
    _enabled = false;
    _generation++;
    _timer?.cancel();
    _timer = null;
  }

  bool _current(int generation) => _enabled && _generation == generation;

  Future<void> _tick() async {
    if (!_enabled || _inFlight) return;
    _inFlight = true;
    final generation = _generation;
    try {
      final session = await attendance.attendanceStatus();
      if (!_current(generation)) return;
      if (session == null || session.clockedOutAt != null) {
        stop();
        onReading(null);
        return;
      }
      final location = await capture();
      if (!_current(generation)) return;
      // Recheck after asynchronous device capture, before any transmission.
      final current = await attendance.attendanceStatus();
      if (!_current(generation)) return;
      if (current == null || current.id != session.id ||
          current.branchId != session.branchId || current.clockedOutAt != null) {
        stop();
        onReading(null);
        return;
      }
      final receipt = await monitoring.submitObservation(current, location);
      if (_current(generation)) onReading(receipt);
    } catch (_) {
      // Missing permission, GPS or network is not an outside-perimeter event.
      if (_current(generation)) onReading(null);
    } finally {
      _inFlight = false;
    }
  }
}
