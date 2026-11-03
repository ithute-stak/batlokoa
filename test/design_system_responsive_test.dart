import 'package:batlokoa/batlokoa_design.dart';
import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Provisional theme uses centralized tokens', () {
    final theme = BatlokoaDesign.theme();
    expect(theme.useMaterial3, isTrue);
    expect(theme.scaffoldBackgroundColor, BatlokoaDesign.canvas);
    expect(theme.colorScheme.primary, BatlokoaDesign.primary);
    expect(theme.textTheme.headlineMedium?.fontWeight, FontWeight.w800);
    expect(BatlokoaDesign.minTapHeight, greaterThanOrEqualTo(48));
  });

  test('Page insets adapt to narrow and desktop screens', () {
    expect(BatlokoaDesign.pagePadding(320).horizontal, 24);
    expect(BatlokoaDesign.pagePadding(375).horizontal, 36);
    expect(BatlokoaDesign.pagePadding(1024).horizontal, 56);
  });

  testWidgets('Six-screen demo remains navigable on narrow mobile',
      (tester) async {
    tester.view.physicalSize = const Size(320, 720);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const BatlokoaApp());
    expect(find.text('Batlokoa Finance'), findsOneWidget);
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();

    for (final tab in ['Loans', 'Wallet', 'Pay bills', 'Profile', 'Home']) {
      final navigation = find.byType(NavigationBar);
      expect(navigation, findsOneWidget);
      final destination = find.descendant(
        of: navigation,
        matching: find.text(tab),
      );
      await tester.tap(destination);
      await tester.pumpAndSettle();
      expect(find.textContaining('DEMO PREVIEW'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('Desktop layout uses navigation rail and readable headers',
      (tester) async {
    tester.view.physicalSize = const Size(1240, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
    expect(find.byType(NavigationRail), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.text('Good morning 👋'), findsOneWidget);
    expect(find.textContaining('DEMO PREVIEW'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
