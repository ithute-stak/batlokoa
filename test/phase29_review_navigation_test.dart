import 'package:batlokoa/main.dart';
import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Confirmation is display-only and is safely repeatable after closing',
      (tester) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(
      home: DemoPaymentReview(
        title: 'Electricity',
        amount: '75.50',
        reference: 'METER-123',
        method: 'Wallet (demo)',
      ),
    ));
    final confirmation = find.text('Preview confirmation');
    await tester.ensureVisible(confirmation);
    await tester.tap(confirmation);
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    expect(find.text(
        'This is a visual preview. No transaction was made and no receipt was issued.'),
        findsOneWidget);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsNothing);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNotNull);
    await tester.tap(confirmation);
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsOneWidget);
  });

  testWidgets('Biller review allows edit then review again with updated draft',
      (tester) async {
    tester.view.physicalSize = const Size(390, 1050);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const MaterialApp(home: PayService(service: 'Electricity')));
    final reference = find.widgetWithText(TextFormField, 'Meter number');
    final amount = find.widgetWithText(TextFormField, 'Amount in LSL');
    await tester.enterText(reference, 'METER-ONE');
    await tester.enterText(amount, '50.00');
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('METER-ONE'), findsOneWidget);
    expect(find.text('M 50.00'), findsOneWidget);
    await tester.ensureVisible(find.text('Edit details'));
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsNothing);
    expect(tester.widget<TextFormField>(reference).controller!.text, 'METER-ONE');
    await tester.enterText(amount, '75.25');
    await tester.ensureVisible(find.text('Review payment'));
    await tester.tap(find.text('Review payment'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.text('M 75.25'), findsOneWidget);
    expect(find.text('M 50.00'), findsNothing);
  });
}
