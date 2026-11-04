import 'package:batlokoa/main.dart';
import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> showForm(WidgetTester tester, Widget screen) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(home: screen));
  }

  testWidgets('Bill explicit edit returns keyboard focus to amount and keeps draft',
      (tester) async {
    await showForm(tester, const PayService(service: 'Electricity'));
    final reference = find.widgetWithText(TextFormField, 'Meter number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(reference, 'METER-001');
    await tester.enterText(amount, '90.00');
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    await tester.ensureVisible(find.text('Edit details'));
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsNothing);
    final field = tester.widget<TextField>(
      find.descendant(of: amount, matching: find.byType(TextField)));
    expect(field.focusNode!.hasFocus, isTrue);
    expect(tester.widget<TextFormField>(reference).controller!.text, 'METER-001');
    expect(tester.widget<TextFormField>(amount).controller!.text, '90.00');
  });

  testWidgets('System back from transfer review restores unsent form',
      (tester) async {
    await showForm(tester, const Transfer(action: 'Send money'));
    final reference =
        find.widgetWithText(TextFormField, 'Recipient / account number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(reference, 'ACCOUNT-DEMO');
    await tester.enterText(amount, '120.50');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsNothing);
    expect(tester.widget<TextFormField>(reference).controller!.text,
        'ACCOUNT-DEMO');
    expect(tester.widget<TextFormField>(amount).controller!.text, '120.50');
  });

  testWidgets('Transfer explicit edit can correct amount and review again',
      (tester) async {
    await showForm(tester, const Transfer(action: 'Send money'));
    final reference =
        find.widgetWithText(TextFormField, 'Recipient / account number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(reference, 'ACCOUNT-DEMO');
    await tester.enterText(amount, '120.50');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    await tester.ensureVisible(find.text('Edit details'));
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(
      find.descendant(of: amount, matching: find.byType(TextField)))
      .focusNode!.hasFocus, isTrue);
    await tester.enterText(amount, '150.75');
    await tester.ensureVisible(find.text('Review transaction'));
    await tester.tap(find.text('Review transaction'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('M 150.75'), findsOneWidget);
    expect(find.text('M 120.50'), findsNothing);
  });
}
