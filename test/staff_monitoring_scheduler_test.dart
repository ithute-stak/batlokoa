import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_location_capture.dart';
import 'package:batlokoa/staff_monitoring_scheduler.dart';

class FakeGateway implements StaffAttendanceGateway, StaffMonitoringGateway {
  StaffAttendanceSession? current = StaffAttendanceSession(
      1, 'branch', DateTime.utc(2026, 11, 26), null);
  int writes = 0;
  bool fail = false;

  @override
  Future<StaffAttendanceSession?> attendanceStatus() async => current;
  @override
  Future<List<StaffAttendanceSession>> attendanceHistory({int limit = 30, int? before}) async => [];
  @override
  Future<void> recordAttendance(String branchId, StaffLocationCapture capture,
      {required bool clockIn}) async => throw UnsupportedError('Not used');
  @override
  Future<StaffMonitorReceipt> submitObservation(
      StaffAttendanceSession session, StaffLocationCapture capture) async {
    writes++;
    if (fail) throw StateError('Network unavailable');
    return StaffMonitorReceipt(session.id, StaffPerimeterReading.inside,
        StaffPerimeterReading.inside, DateTime.now().toUtc(), false);
  }
}

StaffLocationCapture sample() => StaffLocationCapture(
    latitude: -29.31, longitude: 27.48, accuracyM: 2,
    capturedAt: DateTime.now().toUtc());

void main() {
  testWidgets('periodic samples stop after cancellation', (tester) async {
    final gateway = FakeGateway();
    final readings = <StaffMonitorReceipt?>[];
    final scheduler = StaffMonitoringScheduler(attendance: gateway,
      monitoring: gateway, capture: () async => sample(), onReading: readings.add);
    try {
      expect(gateway.writes, 0);
      scheduler.start();
      await tester.pump();
      expect(gateway.writes, 1);
      await tester.pump(const Duration(seconds: 30));
      expect(gateway.writes, 2);
      expect(readings.last?.reading, StaffPerimeterReading.inside);
      scheduler.stop();
      await tester.pump(const Duration(seconds: 60));
      expect(gateway.writes, 2);
    } finally {
      scheduler.stop();
    }
  });

  testWidgets('stop during GPS capture discards pending coordinates', (tester) async {
    final gateway = FakeGateway();
    final pending = Completer<StaffLocationCapture>();
    final readings = <StaffMonitorReceipt?>[];
    final scheduler = StaffMonitoringScheduler(attendance: gateway,
        monitoring: gateway, capture: () => pending.future, onReading: readings.add);
    try {
      scheduler.start();
      await tester.pump();
      await tester.pump(const Duration(seconds: 30));
      scheduler.stop();
      pending.complete(sample());
      await tester.pump();
      expect(gateway.writes, 0);
      expect(readings, isEmpty);
    } finally {
      scheduler.stop();
    }
  });

  testWidgets('clock-out during capture stops without sending GPS', (tester) async {
    final gateway = FakeGateway();
    final pending = Completer<StaffLocationCapture>();
    final readings = <StaffMonitorReceipt?>[];
    final scheduler = StaffMonitoringScheduler(attendance: gateway,
        monitoring: gateway, capture: () => pending.future, onReading: readings.add);
    try {
      scheduler.start();
      await tester.pump();
      gateway.current = null;
      pending.complete(sample());
      await tester.pump();
      expect(gateway.writes, 0);
      expect(scheduler.enabled, isFalse);
      expect(readings, [null]);
    } finally {
      scheduler.stop();
    }
  });

  testWidgets('network failure reports unknown rather than departure', (tester) async {
    final gateway = FakeGateway()..fail = true;
    final readings = <StaffMonitorReceipt?>[];
    final scheduler = StaffMonitoringScheduler(attendance: gateway,
        monitoring: gateway, capture: () async => sample(), onReading: readings.add);
    try {
      scheduler.start();
      await tester.pump();
      expect(gateway.writes, 1);
      expect(readings, [null]);
      expect(scheduler.enabled, isTrue);
    } finally {
      scheduler.stop();
    }
  });

  testWidgets('no active session does not request location', (tester) async {
    final gateway = FakeGateway()..current = null;
    final scheduler = StaffMonitoringScheduler(attendance: gateway,
        monitoring: gateway, capture: () async => throw StateError('Unexpected capture'),
        onReading: (_) {});
    try {
      scheduler.start();
      await tester.pump();
      expect(scheduler.enabled, isFalse);
      expect(gateway.writes, 0);
    } finally {
      scheduler.stop();
    }
  });
}
