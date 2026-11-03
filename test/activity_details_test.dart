import 'package:batlokoa/activity_details.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('sample transaction details clearly reject receipt status', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(builder: (context) => Scaffold(
        body: FilledButton(
          onPressed: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => DemoActivityPage(activity: demoActivities[0]),
            ),
          ),
          child: const Text('Open sample'),
        ),
      )),
    ));

    await tester.tap(find.text('Open sample'));
    await tester.pumpAndSettle();

    expect(find.text('Transaction details'), findsOneWidget);
    expect(find.text('SAMPLE TRANSACTION — NOT A RECEIPT'), findsOneWidget);
    expect(find.text('BTL-SAMPLE-1004'), findsOneWidget);
    expect(find.text('Sample data only'), findsOneWidget);

    await tester.tap(find.text('Back to activity'));
    await tester.pumpAndSettle();
    expect(find.text('Open sample'), findsOneWidget);
  });
}
