import 'package:batlokoa/ui_states.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('loading does not render stale financial information', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(
      body: LoadableView<String>(
        state: Loading<String>(),
        builder: _stringBuilder,
      ),
    )));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Loading your information…'), findsOneWidget);
    expect(find.text('M 500.00'), findsNothing);
  });

  testWidgets('error exposes retry callback', (tester) async {
    var attempts = 0;
    await tester.pumpWidget(MaterialApp(home: Scaffold(
      body: LoadableView<String>(
        state: const Failed<String>('Connection unavailable'),
        builder: _stringBuilder,
        onRetry: () => attempts++,
      ),
    )));
    expect(find.text('Unable to load'), findsOneWidget);
    await tester.tap(find.text('Try again'));
    expect(attempts, 1);
  });

  testWidgets('empty and loaded states are distinct', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(
      body: LoadableView<String>(
        state: Empty<String>(),
        builder: _stringBuilder,
      ),
    )));
    expect(find.text('Nothing to show yet'), findsOneWidget);
    await tester.pumpWidget(const MaterialApp(home: Scaffold(
      body: LoadableView<String>(
        state: Loaded<String>('M 500.00'),
        builder: _stringBuilder,
      ),
    )));
    expect(find.text('M 500.00'), findsOneWidget);
  });
}

Widget _stringBuilder(BuildContext context, String value) => Text(value);
