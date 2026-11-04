import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterDemo(WidgetTester tester, double width) async {
    tester.view.physicalSize = Size(width, 950);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
  }

  testWidgets('Bottom navigation lets customers return to dashboard',
      (tester) async {
    await enterDemo(tester, 390);
    expect(find.byKey(const Key('back-to-dashboard')), findsNothing);
    await tester.tap(find.text('Pay bills').last);
    await tester.pumpAndSettle();
    expect(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == 'Current section: Pay bills. Back to dashboard'), findsOneWidget);
    expect(find.byKey(const Key('back-to-dashboard')), findsOneWidget);
    expect(find.text('Choose a service'), findsOneWidget);
    await tester.tap(find.byKey(const Key('back-to-dashboard')));
    await tester.pumpAndSettle();
    expect(find.text('My active loan'), findsOneWidget);
    expect(find.byKey(const Key('back-to-dashboard')), findsNothing);
    expect(tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex, 0);
  });

  testWidgets('Wide navigation rail has a matching dashboard return action',
      (tester) async {
    await enterDemo(tester, 1200);
    expect(find.byType(NavigationRail), findsOneWidget);
    await tester.tap(find.text('Wallet').last);
    await tester.pumpAndSettle();
    expect(find.byWidgetPredicate((widget) => widget is Semantics && widget.properties.label == 'Current section: Wallet. Back to dashboard'), findsOneWidget);
    expect(find.byKey(const Key('back-to-dashboard')), findsOneWidget);
    await tester.tap(find.byKey(const Key('back-to-dashboard')));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationRail>(find.byType(NavigationRail)).selectedIndex, 0);
    expect(find.text('My active loan'), findsOneWidget);
  });

  testWidgets('Section announcement is an accessible live region',
      (tester) async {
    await enterDemo(tester, 390);
    await tester.tap(find.text('Loans').last);
    await tester.pumpAndSettle();
    expect(
      find.byWidgetPredicate((widget) => widget is Semantics &&
          widget.properties.liveRegion == true &&
          widget.properties.label == 'Current section: Loans. Back to dashboard'),
      findsOneWidget,
    );
  });
}
