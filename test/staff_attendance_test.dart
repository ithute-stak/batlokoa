import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_attendance_screen.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_location_capture.dart';

const branch = '12345678-1234-1234-1234-123456789abc';
const other = '22345678-1234-1234-1234-123456789abc';
const staff = StaffSession(role: 'LOAN_OFFICER', companyId: 'company',
    branchIds: [branch], companyWide: false);

class FakeAttendance implements StaffAttendanceGateway {
  StaffAttendanceSession? current;
  int writes = 0;
  bool failStatus = false;
  bool loseReceipt = false;
  bool outside = false;

  @override
  Future<StaffAttendanceSession?> attendanceStatus() async {
    if (failStatus) throw StateError('Unavailable');
    return current;
  }

  @override
  Future<List<StaffAttendanceSession>> attendanceHistory({int limit = 30, int? before}) async {
    final row = current;
    return row == null ? [] : [row];
  }

  @override
  Future<void> recordAttendance(String branchId, StaffLocationCapture capture,
      {required bool clockIn}) async {
    writes++;
    expect(branchId, branch);
    if (outside) throw StateError('You are outside the authorized office perimeter.');
    current = clockIn ? StaffAttendanceSession(1, branch, DateTime.utc(2026, 11, 26, 5), null) : null;
    if (loseReceipt) {
      failStatus = true;
      throw StateError('Response lost');
    }
  }
}

final button = find.byKey(const Key('staff-attendance-record'));

Future<void> open(WidgetTester tester, FakeAttendance gateway,
    {double accuracy = 2, Map<String, String> branches = const {branch: 'Maseru', other: 'Other'}}) async {
  await tester.pumpWidget(MaterialApp(home: StaffAttendanceScreen(
    staff: staff, gateway: gateway, branches: branches,
    capture: () async => StaffLocationCapture(latitude: -29.31,
      longitude: 27.48, accuracyM: accuracy, capturedAt: DateTime.now()),
  )));
  await tester.pumpAndSettle();
}

Future<void> tapClock(WidgetTester tester) async {
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('clock in and out reflect authoritative status', (tester) async {
    final gateway = FakeAttendance();
    await open(tester, gateway);
    expect(find.text('Clocked out'), findsOneWidget);
    expect(find.text('Other'), findsNothing);
    await tapClock(tester);
    expect(gateway.writes, 1);
    expect(find.text('Clocked in'), findsOneWidget);
    expect(find.text('Clocked in at 2026-11-26 07:00 (Lesotho)'), findsOneWidget);
    await tapClock(tester);
    expect(gateway.writes, 2);
    expect(find.text('Clocked out'), findsOneWidget);
  });

  testWidgets('inaccurate GPS cannot trigger a write', (tester) async {
    final gateway = FakeAttendance();
    await open(tester, gateway, accuracy: 12);
    await tapClock(tester);
    expect(gateway.writes, 0);
    expect(find.textContaining('Location unavailable or inaccurate'), findsOneWidget);
  });

  testWidgets('outside perimeter does not show successful clocking', (tester) async {
    final gateway = FakeAttendance()..outside = true;
    await open(tester, gateway);
    await tapClock(tester);
    expect(find.text('You are outside the authorized office perimeter.'), findsOneWidget);
    expect(find.text('Clocked out'), findsOneWidget);
    expect(find.text('Clock-in recorded.'), findsNothing);
  });

  testWidgets('lost receipt blocks retries until status is refreshed', (tester) async {
    final gateway = FakeAttendance()..loseReceipt = true;
    await open(tester, gateway);
    await tapClock(tester);
    expect(gateway.writes, 1);
    expect(find.text('Attendance status unverified'), findsOneWidget);
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    gateway.failStatus = false;
    await tester.tap(find.byTooltip('Refresh attendance'));
    await tester.pumpAndSettle();
    expect(find.text('Clocked in'), findsOneWidget);
    expect(gateway.writes, 1);
  });

  testWidgets('no authorized branch disables clocking', (tester) async {
    final gateway = FakeAttendance();
    await open(tester, gateway, branches: const {other: 'Other'});
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    expect(gateway.writes, 0);
  });
}
