import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterDemo(WidgetTester tester) async {
    tester.view.physicalSize = const Size(430, 1000);
    tester.view.devicePixelRatio = 1;
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
  }

  testWidgets('Home loan summary opens Loans, details and sample activity',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.ensureVisible(find.text('Manage loan'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Manage loan'));
    await tester.pumpAndSettle();
    expect(find.text('My loans'), findsOneWidget);
    await tester.tap(find.text('View loan details'));
    await tester.pumpAndSettle();
    expect(find.text('Loan details'), findsOneWidget);
    expect(find.text('Sample repayment schedule'), findsOneWidget);
    await tester.ensureVisible(find.text('View sample activity'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('View sample activity'));
    await tester.pumpAndSettle();
    expect(find.text('Transaction history'), findsOneWidget);
    expect(find.textContaining('not financial records'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Back to loans'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Back to loans'));
    await tester.pumpAndSettle();
    expect(find.text('My loans'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Home recent activity opens filtered-capable demo history',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.scrollUntilVisible(
      find.text('Electricity payment'),
      180,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Electricity payment'));
    await tester.pumpAndSettle();
    expect(find.text('Transaction history'), findsOneWidget);
    expect(find.text('Search activity'), findsOneWidget);
    expect(find.text('Money in'), findsOneWidget);
    expect(find.text('Money out'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Home Transfers shortcut opens Send money demo, not a biller',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.ensureVisible(find.text('Transfers'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Transfers'));
    await tester.pumpAndSettle();
    expect(find.text('Send money'), findsWidgets);
    expect(find.text('Method'), findsOneWidget);
    expect(find.text('Review transaction'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('More shortcut is a demo dialog, not a payment form',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.ensureVisible(find.text('More'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('More'));
    await tester.pumpAndSettle();
    expect(find.text('Demo preview'), findsOneWidget);
    expect(find.textContaining('No money moved'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
