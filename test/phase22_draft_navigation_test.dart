import 'package:batlokoa/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> enterDemo(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 950);
    tester.view.devicePixelRatio = 1;
    await tester.pumpWidget(const BatlokoaApp());
    await tester.tap(find.text('Explore demo'));
    await tester.pumpAndSettle();
  }

  testWidgets('Switching tabs retains Home scroll position',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    final homeScroll = find.descendant(
      of: find.byType(IndexedStack),
      matching: find.byType(Scrollable),
    ).first;
    await tester.drag(homeScroll, const Offset(0, -300));
    await tester.pumpAndSettle();
    final before = tester.state<ScrollableState>(homeScroll).position.pixels;
    expect(before, greaterThan(0));
    await tester.tap(find.text('Wallet').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Home').last);
    await tester.pumpAndSettle();
    final after = tester.state<ScrollableState>(homeScroll).position.pixels;
    expect(after, closeTo(before, 1));
  });

  testWidgets('Edited send-money demo can keep editing or discard',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.tap(find.text('Wallet').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Send money').last);
    await tester.pumpAndSettle();
    expect(find.text('Review transaction'), findsOneWidget);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Amount in LSL'), '75.00');
    await tester.pump();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Discard demo draft?'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    expect(find.text('75.00'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Discard draft'));
    await tester.pumpAndSettle();
    expect(find.text('My wallet'), findsOneWidget);
  });

  testWidgets('Unedited bill preview exits without discard dialog',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.tap(find.text('Pay bills').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Electricity'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Electricity'));
    await tester.pumpAndSettle();
    expect(find.text('Review payment'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Pay bills'), findsWidgets);
    expect(find.text('Discard demo draft?'), findsNothing);
  });

  testWidgets('Modified loan application warns before losing draft',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await enterDemo(tester);
    await tester.tap(find.text('Loans').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Start application'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Start application'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Step 2 of 3'), findsOneWidget);
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Discard demo draft?'), findsOneWidget);
    await tester.tap(find.text('Discard draft'));
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex, 1);
    expect(find.text('Step 2 of 3'), findsNothing);
    expect(find.text('Discard demo draft?'), findsNothing);
  });
}
