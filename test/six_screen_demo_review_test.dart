import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Entry clearly labels demo and toggles password visibility',
      (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    expect(find.textContaining('Entered credentials are not submitted'),
        findsOneWidget);
    final field = tester.widget<TextField>(
      find.byType(TextField).last,
    );
    expect(field.obscureText, isTrue);
    await tester.tap(find.byTooltip('Show password'));
    await tester.pump();
    final visible = tester.widget<TextField>(
      find.widgetWithText(TextField, 'Password'),
    );
    expect(visible.obscureText, isFalse);
    expect(find.byTooltip('Hide password'), findsOneWidget);
  });

  testWidgets('Home, Loans, Wallet, Pay bills and Profile display demo notice',
      (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    expect(find.textContaining('DEMO PREVIEW'), findsOneWidget);

    for (final section in ['Loans', 'Wallet', 'Pay bills', 'Profile']) {
      await tester.tap(find.text(section).last);
      await tester.pumpAndSettle();
      expect(find.textContaining('DEMO PREVIEW'), findsOneWidget,
          reason: '$section must disclose that account data is fictional');
    }
  });

  testWidgets('Preview registration never claims real verification',
      (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Create an account'));
    await tester.pump();
    expect(find.text('Preview registration (demo)'), findsOneWidget);
    expect(find.textContaining('No real authentication or money transfers'),
        findsOneWidget);
  });
}
