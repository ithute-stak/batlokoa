import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Payment preview exposes screen-reader summary and warning',
      (tester) async {
    final semantics = tester.ensureSemantics();
    addTearDown(semantics.dispose);
    await tester.pumpWidget(const MaterialApp(
      home: DemoPaymentReview(
        title: 'Electricity',
        amount: '75.50',
        reference: 'METER-123',
        method: 'Wallet (demo)',
      ),
    ));

    for (final label in [
      'Service: Electricity',
      'Amount: M 75.50',
      'Reference: METER-123',
      'Payment method: Wallet (demo)',
      'Provider fees: Not available in demo',
      'Demo preview only. No money will be sent.',
    ]) {
      expect(
        find.byWidgetPredicate(
          (widget) => widget is Semantics &&
              widget.properties.label == label,
        ),
        findsOneWidget,
        reason: label,
      );
    }
    expect(find.text('No money will be sent. This summary uses the details you entered.'),
        findsOneWidget);
  });

  testWidgets('Preview confirmation never represents a successful payment',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: DemoPaymentReview(
        title: 'Send money',
        amount: '100.00',
        reference: 'SAMPLE-100',
        method: 'M-Pesa',
      ),
    ));
    await tester.tap(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsOneWidget);
    expect(find.text(
      'This is a visual preview. No transaction was made and no receipt was issued.',
    ), findsOneWidget);
  });
}
