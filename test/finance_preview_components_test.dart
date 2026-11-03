import 'package:batlokoa/demo_finance_components.dart';
import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Balance card clearly labels fictional funds', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: DemoBalanceCard(
        label: 'Sample wallet balance',
        amount: 'M 2,450.00',
        disclaimer: 'Fictional amount')),
    ));
    expect(find.text('DEMO ACCOUNT'), findsOneWidget);
    expect(find.text('Sample wallet balance'), findsOneWidget);
    expect(find.text('Fictional amount'), findsOneWidget);
  });

  testWidgets('Repayment preview never presents a real amount due',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(
        child: DemoRepaymentPreview())),
    ));
    expect(find.text('Sample repayment schedule'), findsOneWidget);
    expect(find.textContaining('not amounts owed'), findsOneWidget);
    expect(find.text('Sample repayment'), findsNWidgets(3));
  });

  testWidgets('Wallet action grid passes only demo action labels',
      (tester) async {
    String? action;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: SizedBox(
        width: 340,
        child: DemoWalletActions(onAction: (value) => action = value))),
    ));
    expect(find.text('Add money'), findsOneWidget);
    expect(find.text('Send money'), findsOneWidget);
    await tester.tap(find.text('Send money'));
    expect(action, 'Send money');
  });

  testWidgets('Home and wallet show separate fictional balance cards',
      (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    expect(find.byType(DemoBalanceCard), findsOneWidget);
    expect(find.text('DEMO ACCOUNT'), findsOneWidget);
    await tester.tap(find.text('Wallet').last);
    await tester.pumpAndSettle();
    expect(find.byType(DemoBalanceCard), findsOneWidget);
    expect(find.byType(DemoWalletActions), findsOneWidget);
    expect(find.text('DEMO ACCOUNT'), findsOneWidget);
  });
}
