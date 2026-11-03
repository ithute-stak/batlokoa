import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Batlokoa launches with demo entry point', (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    expect(find.text('Batlokoa Finance'), findsOneWidget);
    expect(find.text('Explore demo'), findsOneWidget);
  });
}
