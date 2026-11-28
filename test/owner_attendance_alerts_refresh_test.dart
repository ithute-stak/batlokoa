import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/owner_attendance_alerts_screen.dart';

class FakeInbox implements OwnerAttendanceInboxGateway {
  final List<OwnerAttendanceAlert> rows = [];
  int reads = 0;
  bool denied = false;
  Completer<OwnerAttendanceAlertPage>? pending;

  @override
  Future<OwnerAttendanceAlertPage> attendanceAlerts({int after = 0, int limit = 50}) async {
    reads++;
    if (denied) throw StateError('Access denied');
    if (pending != null) return pending!.future;
    final eligible = rows.where((row) => row.id > after).toList()
      ..sort((a, b) => a.id.compareTo(b.id));
    final page = eligible.take(limit).toList();
    return OwnerAttendanceAlertPage(
      page, page.isEmpty ? after : page.last.id, eligible.length > limit);
  }
}

OwnerAttendanceAlert alert(int id, {bool outside = true}) => OwnerAttendanceAlert(
    id, 7, 'employee-$id', 'branch', outside
        ? 'reported_outside_perimeter' : 'reported_inside_perimeter',
    DateTime.utc(2026, 11, 26, 6));

Future<void> openInbox(WidgetTester tester, FakeInbox gateway) async {
  await tester.pumpWidget(MaterialApp(home: OwnerAttendanceAlertsScreen(gateway: gateway)));
  await tester.pump();
  await tester.pump();
}

Future<void> closeInbox(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
}

void main() {
  testWidgets('shows resolved names instead of raw identifiers', (tester) async {
    final gateway = FakeInbox()..rows.add(OwnerAttendanceAlert(
      1, 7, 'employee-1', 'branch-1', 'reported_outside_perimeter',
      DateTime.utc(2026, 11, 26, 6),
      employeeName: 'Example Employee', branchName: 'Maseru Office',
    ));
    await openInbox(tester, gateway);
    try {
      expect(find.textContaining('Employee: Example Employee'), findsOneWidget);
      expect(find.textContaining('Branch: Maseru Office'), findsOneWidget);
      expect(find.textContaining('employee-1'), findsNothing);
      expect(find.textContaining('branch-1'), findsNothing);
    } finally {
      await closeInbox(tester);
    }
  });

  testWidgets('unresolved labels retain explicit identifier fallback', (tester) async {
    final gateway = FakeInbox()..rows.add(alert(1));
    await openInbox(tester, gateway);
    try {
      expect(find.textContaining('Employee: Unknown name (ID: employee-1)'), findsOneWidget);
      expect(find.textContaining('Branch: Unknown name (ID: branch)'), findsOneWidget);
    } finally {
      await closeInbox(tester);
    }
  });

  testWidgets('poll reconciles late committed lower IDs without duplicates', (tester) async {
    final gateway = FakeInbox()..rows.add(alert(2));
    await openInbox(tester, gateway);
    try {
      expect(find.text('Reported outside office perimeter'), findsOneWidget);
      gateway.rows.add(alert(1, outside: false));
      await tester.pump(const Duration(seconds: 30));
      await tester.pump();
      expect(find.text('Reported return inside perimeter'), findsOneWidget);
      expect(find.text('Reported outside office perimeter'), findsOneWidget);
      await tester.pump(const Duration(seconds: 30));
      await tester.pump();
      expect(find.text('Reported return inside perimeter'), findsOneWidget);
      expect(find.text('Reported outside office perimeter'), findsOneWidget);
      expect(gateway.reads, 3);
    } finally {
      await closeInbox(tester);
    }
  });

  testWidgets('failed refresh clears previously visible alerts and pauses polling', (tester) async {
    final gateway = FakeInbox()..rows.add(alert(1));
    await openInbox(tester, gateway);
    try {
      expect(find.text('Reported outside office perimeter'), findsOneWidget);
      gateway.denied = true;
      await tester.pump(const Duration(seconds: 30));
      await tester.pump();
      expect(find.text('Reported outside office perimeter'), findsNothing);
      expect(find.text('Attendance alerts unavailable or access denied.'), findsOneWidget);
      final reads = gateway.reads;
      await tester.pump(const Duration(seconds: 60));
      expect(gateway.reads, reads);
      gateway.denied = false;
      await tester.tap(find.byTooltip('Refresh alerts'));
      await tester.pump();
      await tester.pump();
      expect(find.text('Reported outside office perimeter'), findsOneWidget);
    } finally {
      await closeInbox(tester);
    }
  });

  testWidgets('closing inbox cancels polling and ignores delayed response', (tester) async {
    final gateway = FakeInbox()..rows.add(alert(1));
    await openInbox(tester, gateway);
    final pending = Completer<OwnerAttendanceAlertPage>();
    gateway.pending = pending;
    await tester.pump(const Duration(seconds: 30));
    await tester.pump();
    final reads = gateway.reads;
    await tester.pump(const Duration(seconds: 30));
    expect(gateway.reads, reads);
    await closeInbox(tester);
    pending.complete(OwnerAttendanceAlertPage([alert(2)], 2, false));
    await tester.pump(const Duration(seconds: 60));
    expect(gateway.reads, reads);
    expect(tester.takeException(), isNull);
  });
}
