import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> showReview(WidgetTester tester) async {
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
  }

  testWidgets('Closing demo confirmation displays no-payment status', (tester) async {
    await showReview(tester);
    expect(find.byKey(const Key('demo-preview-closed-status')), findsNothing);
    await tester.ensureVisible(find.text('Preview confirmation'));
    await tester.tap(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('demo-preview-closed-status')), findsOneWidget);
    expect(find.text('M 75.50'), findsOneWidget);
    expect(find.text('METER-123'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNotNull);
  });

  testWidgets('System back dismisses preview dialog and preserves review',
      (tester) async {
    await showReview(tester);
    await tester.ensureVisible(find.text('Preview confirmation'));
    await tester.tap(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsOneWidget);
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.text('Demo complete'), findsNothing);
    expect(find.byType(DemoPaymentReview), findsOneWidget);
    expect(find.byKey(const Key('demo-preview-closed-status')), findsOneWidget);
    expect(find.text('M 75.50'), findsOneWidget);
  });

  testWidgets('Closed preview status announced in live region', (tester) async {
    await showReview(tester);
    await tester.ensureVisible(find.text('Preview confirmation'));
    await tester.tap(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(
      find.byWidgetPredicate((widget) => widget is Semantics &&
          widget.properties.liveRegion == true &&
          widget.properties.label ==
              'Preview closed. No payment was made. Your details are unchanged.'),
      findsOneWidget,
    );
  });
}
