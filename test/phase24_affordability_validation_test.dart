import 'package:batlokoa/input_validators.dart';
import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Loan income requires positive, finite, bounded money with at most two decimals', () {
    for (final value in ['', '0', '-1', 'NaN', 'Infinity', '1e3',
      '10.999', '1000000.01', '999999999999999999999999999999999999999999999999']) {
      expect(DemoInputValidator.monthlyIncome(value), isNotNull,
          reason: 'Must reject: $value');
    }
    for (final value in ['0.01', '1500', '1500.25', '1000000.00']) {
      expect(DemoInputValidator.monthlyIncome(value), isNull,
          reason: 'Must accept: $value');
    }
  });

  test('Income source requires a reasonable nonempty label', () {
    expect(DemoInputValidator.incomeSource('  '), isNotNull);
    expect(DemoInputValidator.incomeSource(List.filled(121, 'x').join()), isNotNull);
    expect(DemoInputValidator.incomeSource('Sample employment'), isNull);
  });

  testWidgets('Loan demo rejects an out-of-range income and recovers without losing draft', (tester) async {
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
    await tester.enterText(source, 'Sample employment');
    await tester.enterText(income, '1000000.01');
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 2 of 3'), findsOneWidget);
    expect(find.text('Enter your income source and a valid monthly income.'), findsOneWidget);
    await tester.enterText(income, '2500.50');
    await tester.pumpAndSettle();
    expect(find.text('Enter your income source and a valid monthly income.'), findsNothing);
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 3 of 3'), findsOneWidget);
    expect(find.text('Sample employment'), findsOneWidget);
    expect(find.text('M 2500.50'), findsOneWidget);
  });
}
