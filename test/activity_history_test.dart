import 'package:batlokoa/activity_history.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('search filters demo transaction history and opens details', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ActivityHistoryPage()));
    expect(find.text('Electricity purchase'), findsOneWidget);
    expect(find.text('Wallet top-up'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('activity-search')), 'Electricity');
    await tester.pumpAndSettle();
    expect(find.text('Electricity purchase'), findsOneWidget);
    expect(find.text('Wallet top-up'), findsNothing);
    await tester.tap(find.text('Electricity purchase'));
    await tester.pumpAndSettle();
    expect(find.text('SAMPLE TRANSACTION — NOT A RECEIPT'), findsOneWidget);
  });

  testWidgets('empty history search can reset all filters', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ActivityHistoryPage()));
    await tester.enterText(find.byKey(const Key('activity-search')), 'no-match-1234');
    await tester.pumpAndSettle();

    expect(find.text('No matching transactions'), findsOneWidget);
    await tester.tap(find.text('Show all activity'));
    await tester.pumpAndSettle();

    expect(find.text('Electricity purchase'), findsOneWidget);
    expect(find.text('No matching transactions'), findsNothing);
    expect(find.byType(TextField), findsOneWidget);
  });

  testWidgets('money-in filter shows credits only', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: ActivityHistoryPage()));
    await tester.tap(find.text('Money in'));
    await tester.pumpAndSettle();
    expect(find.text('Wallet top-up'), findsOneWidget);
    expect(find.text('Electricity purchase'), findsNothing);
  });
}
