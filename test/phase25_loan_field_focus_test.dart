import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Loan form focuses the first invalid field, then the income field',
      (tester) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Loans').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Start application'));
    await tester.tap(find.text('Start application'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();

    final source = find.widgetWithText(TextField, 'Employment / income source');
    final income = find.widgetWithText(TextField, 'Monthly income in LSL');
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(source).focusNode!.hasFocus, isTrue);
    expect(find.text('Income source is required'), findsOneWidget);

    await tester.enterText(source, 'Sample employment');
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(income).focusNode!.hasFocus, isTrue);
    expect(find.text('Enter a monthly income with at most 2 decimal places'),
        findsOneWidget);
    expect(find.text('Step 2 of 3'), findsOneWidget);

    await tester.enterText(income, '2500.50');
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 3 of 3'), findsOneWidget);
    expect(find.text('Sample employment'), findsOneWidget);
  });
}
