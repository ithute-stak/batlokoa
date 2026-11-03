import 'package:batlokoa/main.dart';
import 'package:batlokoa/payment_review.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('transaction review shows entered details without submitting', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: DemoPaymentReview(
        title: 'Electricity',
        amount: '120.00',
        reference: 'METER-DEMO',
        method: 'Wallet (demo)',
      ),
    ));
    expect(find.text('M 120.00'), findsOneWidget);
    expect(find.text('METER-DEMO'), findsOneWidget);
    expect(find.text('No money will be sent. This summary uses the details you entered.'), findsOneWidget);
    await tester.ensureVisible(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Preview confirmation'));
    await tester.pumpAndSettle();
    expect(find.textContaining('No transaction was made'), findsOneWidget);
  });

  testWidgets('review screen returns to edit form', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) => Scaffold(
        body: Center(child: FilledButton(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const DemoPaymentReview(
              title: 'Airtime',
              amount: '10',
              reference: '50000000',
              method: 'Wallet',
            )),
          ),
          child: const Text('Open review'),
        )),
      )),
    ));
    await tester.tap(find.text('Open review'));
    await tester.pumpAndSettle();
    expect(find.text('Review payment'), findsOneWidget);
    await tester.ensureVisible(find.text('Edit details'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Edit details'));
    await tester.pumpAndSettle();
    expect(find.text('Open review'), findsOneWidget);
  });

  testWidgets('profile has customer verification and support navigation', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    expect(find.text('Identity verification'), findsOneWidget);
    await tester.ensureVisible(find.text('Identity verification'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Identity verification'));
    await tester.pumpAndSettle();
    expect(find.text('Verify your identity'), findsOneWidget);
  });
}
