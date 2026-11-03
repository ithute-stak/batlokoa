import 'package:batlokoa/main.dart';
import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Long loan details stack when text is enlarged',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(2)),
          child: SizedBox(
            width: 270,
            child: Detail('Next loan instalment due date', '15 Nov 2026'),
          ),
        ),
      ),
    ));
    expect(find.text('Next loan instalment due date'), findsOneWidget);
    expect(find.text('15 Nov 2026'), findsOneWidget);
    expect(find.byType(Column), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Payment review presents all amounts at large text scale',
      (tester) async {
    tester.view.physicalSize = const Size(375, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          textScaler: const TextScaler.linear(1.8)),
        child: child!,
      ),
      home: const DemoPaymentReview(
        title: 'Electricity',
        amount: '200.00',
        reference: 'TEST-DEMO-001',
        method: 'Wallet (demo)',
      ),
    ));
    expect(find.text('M 200.00'), findsOneWidget);
    expect(find.text('TEST-DEMO-001'), findsOneWidget);
    expect(find.text('Preview confirmation'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Demo login offers keyboard next and done actions',
      (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    final inputs = tester.widgetList<TextField>(find.byType(TextField)).toList();
    expect(inputs.length, 2);
    expect(inputs.first.textInputAction, TextInputAction.next);
    expect(inputs.last.textInputAction, TextInputAction.done);
    expect(inputs.last.obscureText, isTrue);
  });

  testWidgets('Loan and wallet detail labels remain visible on small screens',
      (tester) async {
    tester.view.physicalSize = const Size(320, 740);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Loans').last);
    await tester.pumpAndSettle();
    expect(find.text('Sample loan balance (demo)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
