import 'dart:async';
import 'package:batlokoa/owner_access_events_screen.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Gateway implements OwnerAccessInboxGateway {
  final calls = <OwnerAccessCursor?>[];
  late Future<OwnerAccessEventPage> Function(OwnerAccessCursor?) answer;
  @override
  Future<OwnerAccessEventPage> accessEvents({OwnerAccessCursor? before, int limit = 50}) {
    calls.add(before);
    expect(limit, 50);
    return answer(before);
  }
}

final _newest = OwnerAccessEvent('new', 'employee-a', 'reported_login_outside',
  DateTime.utc(2026, 11, 26, 5, 42), branchId: 'branch-a',
  employeeName: 'Synthetic Alice', branchName: 'Synthetic Office');
final _older = OwnerAccessEvent('old', 'employee-b', 'staff_logged_out',
  DateTime.utc(2026, 11, 26, 5, 31));
const _cursor = OwnerAccessCursor('2026-11-26T05:42:00Z', 'new');

Future<void> _open(WidgetTester tester, _Gateway gateway) async {
  await tester.binding.setSurfaceSize(const Size(800, 1000));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(home: OwnerAccessEventsScreen(gateway: gateway)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('renders names, local time and older access history', (tester) async {
    final gateway = _Gateway()..answer = (before) async => before == null
        ? OwnerAccessEventPage([_newest], _cursor)
        : OwnerAccessEventPage([_older], null);
    await _open(tester, gateway);
    expect(find.text('Reported login outside office'), findsOneWidget);
    expect(find.textContaining('Synthetic Alice'), findsOneWidget);
    expect(find.textContaining('Synthetic Office'), findsOneWidget);
    expect(find.textContaining('07:42:00 (Lesotho)'), findsOneWidget);
    await tester.tap(find.text('Load older events'));
    await tester.pumpAndSettle();
    expect(gateway.calls, [null, _cursor]);
    expect(find.text('Employee signed out'), findsOneWidget);
    expect(find.textContaining('Branch: Not determined'), findsOneWidget);
    expect(find.text('Load older events'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('foreground refresh returns to newest page', (tester) async {
    final gateway = _Gateway()..answer = (_) async => OwnerAccessEventPage([_newest], null);
    await _open(tester, gateway);
    gateway.answer = (_) async => OwnerAccessEventPage([_older], null);
    await tester.pump(const Duration(seconds: 30));
    await tester.pumpAndSettle();
    expect(gateway.calls, [null, null]);
    expect(find.text('Reported login outside office'), findsNothing);
    expect(find.text('Employee signed out'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('authorization failure clears previously displayed history', (tester) async {
    final gateway = _Gateway()..answer = (_) async => OwnerAccessEventPage([_newest], null);
    await _open(tester, gateway);
    gateway.answer = (_) async => throw StateError('Access denied');
    await tester.tap(find.byTooltip('Refresh access events'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Synthetic Alice'), findsNothing);
    expect(find.text('Access events unavailable or access denied.'), findsOneWidget);
    await tester.pump(const Duration(seconds: 30));
    expect(gateway.calls.length, 2);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('late response after disposal is ignored', (tester) async {
    final pending = Completer<OwnerAccessEventPage>();
    final gateway = _Gateway()..answer = (_) => pending.future;
    await tester.pumpWidget(MaterialApp(home: OwnerAccessEventsScreen(gateway: gateway)));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    pending.complete(OwnerAccessEventPage([_newest], null));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
