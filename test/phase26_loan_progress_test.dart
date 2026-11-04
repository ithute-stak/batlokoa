import 'package:batlokoa/demo_loan_progress.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  for (final entry in const [
    (step: 0, label: 'Step 1 of 3: Choose your loan'),
    (step: 1, label: 'Step 2 of 3: Affordability details'),
    (step: 2, label: 'Step 3 of 3: Review your request'),
  ]) {
    testWidgets('Loan step ${entry.step + 1} has accessible progress', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: DemoLoanProgress(step: entry.step)),
      ));
      expect(find.text('Step ${entry.step + 1} of 3'), findsOneWidget);
      expect(
        find.byWidgetPredicate((widget) =>
            widget is Semantics &&
            widget.properties.liveRegion == true &&
            widget.properties.label == entry.label),
        findsOneWidget,
      );
      expect(
        tester.widget<LinearProgressIndicator>(
          find.byType(LinearProgressIndicator),
        ).value,
        closeTo((entry.step + 1) / 3, 0.001),
      );
    });
  }
}
