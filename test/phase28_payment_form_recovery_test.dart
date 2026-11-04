import 'package:batlokoa/demo_form_error.dart';
import 'package:batlokoa/main.dart';
import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterScreen(WidgetTester tester, Widget screen) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(home: screen));
  }

  testWidgets('Transfer focuses reference then amount and preserves corrected fields',
      (tester) async {
    await enterScreen(tester, const Transfer(action: 'Send money'));
    final reference = find.widgetWithText(TextFormField, 'Recipient / account number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsOneWidget);
    expect(tester.widget<TextField>(find.descendant(of:reference,matching:find.byType(TextField))).focusNode!.hasFocus, isTrue);

    await tester.enterText(reference, 'SAMPLE-ACCOUNT');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.descendant(of:amount,matching:find.byType(TextField))).focusNode!.hasFocus, isTrue);

    await tester.enterText(amount, '125.50');
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsNothing);
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('SAMPLE-ACCOUNT'), findsOneWidget);
    expect(find.text('M 125.50'), findsOneWidget);
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextFormField>(reference).controller!.text, 'SAMPLE-ACCOUNT');
    expect(tester.widget<TextFormField>(amount).controller!.text, '125.50');
  });

  testWidgets('Bill payment focuses invalid input and retains draft on review back',
      (tester) async {
    await enterScreen(tester, const PayService(service: 'Electricity'));
    final reference = find.widgetWithText(TextFormField, 'Meter number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(amount, '0');
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsOneWidget);
    expect(tester.widget<TextField>(find.descendant(of:reference,matching:find.byType(TextField))).focusNode!.hasFocus, isTrue);

    await tester.enterText(reference, 'METER-DEMO-001');
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.descendant(of:amount,matching:find.byType(TextField))).focusNode!.hasFocus, isTrue);
    expect(find.text('Enter a positive amount up to M 1,000,000'), findsOneWidget);

    await tester.enterText(amount, '75.50');
    await tester.pumpAndSettle();
    expect(find.byType(DemoFormError), findsNothing);
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('METER-DEMO-001'), findsOneWidget);
    await tester.ensureVisible(find.text('Edit details'));
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextFormField>(reference).controller!.text, 'METER-DEMO-001');
    expect(tester.widget<TextFormField>(amount).controller!.text, '75.50');
  });

  testWidgets('Loan repayment preview requires only an amount',
      (tester) async {
    await enterScreen(tester, const Transfer(action: 'Repay loan'));
    expect(find.text('Recipient / account number'), findsNothing);
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    expect(tester.widget<TextField>(find.descendant(of:amount,matching:find.byType(TextField))).focusNode!.hasFocus, isTrue);
    await tester.enterText(amount, '50.00');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('BTL-DEMO-1001'), findsOneWidget);
  });
}
