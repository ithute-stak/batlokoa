import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/batlokoa_design.dart';
import 'package:batlokoa/batlokoa_logo.dart';
import 'package:batlokoa/main.dart';

void main() {
  test('BFS theme uses established Batlokoa colours and identity', () {
    expect(BatlokoaDesign.primary, const Color(0xFFD71920));
    expect(BatlokoaDesign.accent, const Color(0xFF075EB6));
    expect(BatlokoaDesign.navy, const Color(0xFF12233F));
    expect(BatlokoaDesign.silver, const Color(0xFF667085));
    expect(BatlokoaDesign.theme().colorScheme.primary, BatlokoaDesign.primary);
    expect(BatlokoaDesign.theme().colorScheme.secondary, BatlokoaDesign.accent);
    expect(BatlokoaDesign.companyName, 'Batlokoa Financial Services');
    expect(BatlokoaDesign.motto, 'We make Your Debt Affordable.');
  });

  testWidgets('welcome screen displays Batlokoa company identity', (tester) async {
    await tester.pumpWidget(const BatlokoaApp());
    expect(find.text(BatlokoaDesign.companyName), findsOneWidget);
    expect(find.text(BatlokoaDesign.motto), findsOneWidget);
    expect(find.byType(BatlokoaLogo), findsWidgets);
    expect(find.text('Borrow smarter. Pay easier.'), findsNothing);
  });
}
