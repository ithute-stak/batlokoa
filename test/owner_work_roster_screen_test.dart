import 'dart:async';
import 'package:batlokoa/owner_work_roster_screen.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const employee = OwnerRosterEmployee('employee-a', 'LOAN_OFFICER', 'Synthetic Employee');

class _Gateway implements OwnerWorkRosterGateway, OwnerRosterEmployeeGateway {
  bool? working;
  bool deny = false, failWrite = false;
  int writes = 0, reads = 0;
  String? savedDate;
  Completer<List<OwnerRosterEmployee>>? pending;
  @override
  Future<List<OwnerRosterEmployee>> rosterEmployees() async {
    if (deny) throw StateError('Access denied');
    if (pending != null) return pending!.future;
    return [employee];
  }
  @override
  Future<OwnerWorkRosterPage> workRoster(String workDate, {String? after, int limit = 50}) async {
    reads++;
    return OwnerWorkRosterPage([
      if (working != null)
        OwnerWorkRosterRow(employee.employeeId, working!, 'owner-a', DateTime.utc(2026, 11, 26)),
    ], null);
  }
  @override
  Future<bool> setWorkDay(String employeeId, String workDate, {required bool scheduledToWork}) async {
    expect(employeeId, employee.employeeId);
    writes++;
    savedDate = workDate;
    if (failWrite) throw StateError('Unconfirmed');
    working = scheduledToWork;
    return true;
  }
}

Future<void> open(WidgetTester tester, _Gateway gateway) async {
  await tester.pumpWidget(MaterialApp(home: OwnerWorkRosterScreen(roster: gateway, directory: gateway)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('unknown schedule is not assumed to be a working day', (tester) async {
    final gateway = _Gateway();
    await open(tester, gateway);
    expect(find.text('Synthetic Employee'), findsOneWidget);
    expect(find.text('Schedule unknown'), findsOneWidget);
    expect(gateway.writes, 0);
  });

  testWidgets('cancel leaves schedule unchanged; confirmation refreshes server data', (tester) async {
    final gateway = _Gateway();
    await open(tester, gateway);
    await tester.tap(find.text('Working'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 0);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 0);
    await tester.tap(find.text('Working'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 1);
    expect(gateway.reads, 2);
    expect(find.text('Working day'), findsOneWidget);
    expect(find.text('Schedule confirmed by server.'), findsOneWidget);
    expect(gateway.savedDate, isNotNull);
  });

  testWidgets('failed write does not optimistically change schedule', (tester) async {
    final gateway = _Gateway()..working = true..failWrite = true;
    await open(tester, gateway);
    await tester.tap(find.text('Non-working'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Confirm'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 1);
    expect(gateway.reads, 2);
    expect(find.text('Working day'), findsOneWidget);
    expect(find.textContaining('Update not confirmed.'), findsOneWidget);
  });

  testWidgets('directory authorization failure clears previously displayed employees', (tester) async {
    final gateway = _Gateway();
    await open(tester, gateway);
    gateway.deny = true;
    await tester.tap(find.byTooltip('Refresh working schedules'));
    await tester.pumpAndSettle();
    expect(find.text('Synthetic Employee'), findsNothing);
    expect(find.text('Working'), findsNothing);
    expect(find.textContaining('access denied'), findsOneWidget);
  });

  testWidgets('late directory response after disposal is ignored', (tester) async {
    final gateway = _Gateway()..pending = Completer<List<OwnerRosterEmployee>>();
    await tester.pumpWidget(MaterialApp(home: OwnerWorkRosterScreen(roster: gateway, directory: gateway)));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    gateway.pending!.complete([employee]);
    await tester.pump();
    expect(gateway.reads, 0);
    expect(tester.takeException(), isNull);
  });
}
