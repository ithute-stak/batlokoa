import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterDemo(WidgetTester tester, double width) async {
    tester.view.physicalSize = Size(width, 1000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
  }

  testWidgets('Dashboard wallet shortcut selects wallet tab and returns home',
      (tester) async {
    await enterDemo(tester, 390);
    await tester.ensureVisible(find.byKey(const Key('home-wallet-overview')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('home-wallet-overview')));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex, 2);
    expect(find.text('Current section: Wallet'), findsNothing);
    expect(find.byKey(const Key('back-to-dashboard')), findsOneWidget);
    await tester.tap(find.byKey(const Key('back-to-dashboard')));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex, 0);
    expect(find.byKey(const Key('home-wallet-overview')), findsOneWidget);
  });

  testWidgets('Dashboard all-bills shortcut selects bill services on wide layout',
      (tester) async {
    await enterDemo(tester, 1200);
    expect(find.byType(NavigationRail), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('home-all-bills')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('home-all-bills')));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex, 3);
    expect(find.text('Choose a service'), findsOneWidget);
    await tester.tap(find.byKey(const Key('back-to-dashboard')));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex, 0);
  });

  testWidgets('Wallet and bill links clearly disclose demo-only behavior',
      (tester) async {
    await enterDemo(tester, 390);
    await tester.ensureVisible(find.byKey(const Key('home-wallet-overview')));
    await tester.pumpAndSettle();
    expect(
      find.text('Explore sample payment services or open an account overview. No funds will move.'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('home-all-bills')), findsOneWidget);
  });
}
