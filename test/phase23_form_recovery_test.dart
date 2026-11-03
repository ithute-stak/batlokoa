import 'package:batlokoa/demo_form_error.dart';
import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterDemo(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
  }

  testWidgets('Loan affordability errors are inline and clear after editing',
      (tester) async {
    await enterDemo(tester);
    await tester.tap(find.text('Loans').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Start application'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Start application'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 2 of 3'), findsOneWidget);
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsOneWidget);
    expect(find.text('Enter your income source and a valid monthly income.'),
        findsOneWidget);
    expect(find.text('Step 2 of 3'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextField, 'Employment / income source'),
      'Sample employment',
    );
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsNothing);
    await tester.enterText(
      find.widgetWithText(TextField, 'Monthly income in LSL'), '1500');
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Continue'));
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 3 of 3'), findsOneWidget);
    expect(find.textContaining('Not a loan offer'), findsOneWidget);
  });

  testWidgets('Biller payment inputs show validation during editing',
      (tester) async {
    await enterDemo(tester);
    await tester.tap(find.text('Pay bills').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Electricity'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Electricity'));
    await tester.pumpAndSettle();
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(amount, '0');
    await tester.pumpAndSettle();
    expect(find.text('Enter a positive amount up to M 1,000,000'),
        findsOneWidget);
    await tester.enterText(amount, '75.50');
    await tester.pumpAndSettle();
    expect(find.text('Enter a positive amount up to M 1,000,000'),
        findsNothing);
    expect(find.text('Review payment'), findsOneWidget);
  });

  testWidgets('Inline error exposes a screen-reader live region',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body:
      DemoFormError(message:'Enter valid demo details'))));
    final semantics = tester.widget<Semantics>(find.byType(Semantics).first);
    expect(semantics.properties.liveRegion, isTrue);
    expect(semantics.properties.label, contains('Form error:'));
    expect(find.text('Enter valid demo details'), findsOneWidget);
  });
}
