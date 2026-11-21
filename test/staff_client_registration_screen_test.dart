import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_client_registration_screen.dart';

const assigned = StaffSession(
  role: 'LOAN_OFFICER', companyId: 'test-company',
  branchIds: ['test-branch'], companyWide: false,
);

Future<void> showForm(WidgetTester tester, {StaffSession staff = assigned}) async {
  await tester.pumpWidget(MaterialApp(home:
      StaffClientRegistrationScreen(staff: staff)));
  await tester.pumpAndSettle();
}

Future<void> enter(WidgetTester tester, String key, String value) async {
  final widget = find.byKey(Key('register-$key'));
  if (widget.evaluate().isEmpty) {
    await tester.scrollUntilVisible(widget, 180,
        scrollable: find.byType(Scrollable).first);
  } else {
    await tester.ensureVisible(widget);
  }
  await tester.pumpAndSettle();
  await tester.enterText(widget, value);
}

void main() {
  testWidgets('invalid client details never produce a review or submission',
      (tester) async {
    await showForm(tester);
    await tester.testTextInput.hide();
    await tester.scrollUntilVisible(find.byKey(const Key('register-review')),
        180, scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('register-review')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-review-summary')), findsNothing);
    expect(find.text('Submit registration — unavailable'), findsOneWidget);
    final submit = tester.widget<OutlinedButton>(
        find.widgetWithText(OutlinedButton, 'Submit registration — unavailable'));
    expect(submit.onPressed, isNull);
  });

  testWidgets('valid local draft produces non-submitting masked review',
      (tester) async {
    await showForm(tester);
    await enter(tester, 'first-name', 'Palesa');
    await enter(tester, 'last-name', 'Mokoena');
    await enter(tester, 'phone', '59000000');
    await enter(tester, 'date-of-birth', '1990-01-01');
    await enter(tester, 'gender', 'Female');
    await enter(tester, 'district', 'Maseru');
    await enter(tester, 'employment-status', 'Employed');
    await enter(tester, 'national-id', 'TEST-NATIONAL-ID');
    await enter(tester, 'monthly-income', '1250.00');
    await tester.testTextInput.hide();
    await tester.scrollUntilVisible(find.byKey(const Key('register-review')),
        180, scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('register-review')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-review-summary')), findsOneWidget);
    expect(find.textContaining('Palesa Mokoena'), findsOneWidget);
    expect(find.textContaining('test-branch'), findsWidgets);
    expect(find.textContaining('TEST-NATIONAL-ID'), findsNothing);
    expect(find.text('Submit registration — unavailable'), findsOneWidget);
  });

  testWidgets('missing verified branch cannot prepare registration',
      (tester) async {
    await showForm(tester, staff: const StaffSession(
      role: 'LOAN_OFFICER', companyId: 'test-company',
      branchIds: [], companyWide: false,
    ));
    final review = tester.widget<FilledButton>(
        find.byKey(const Key('register-review')));
    expect(review.onPressed, isNull);
    expect(find.textContaining('No verified branch is available'), findsOneWidget);
  });

  testWidgets('changing values clears previous review',
      (tester) async {
    await showForm(tester);
    await enter(tester, 'first-name', 'Palesa');
    await enter(tester, 'last-name', 'Mokoena');
    await enter(tester, 'phone', '59000000');
    await enter(tester, 'date-of-birth', '1990-01-01');
    await enter(tester, 'gender', 'Female');
    await enter(tester, 'district', 'Maseru');
    await enter(tester, 'employment-status', 'Employed');
    await enter(tester, 'passport-number', 'TEST-PASSPORT');
    await tester.testTextInput.hide();
    await tester.scrollUntilVisible(find.byKey(const Key('register-review')),
        180, scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('register-review')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-review-summary')), findsOneWidget);
    final firstName = find.byKey(const Key('register-first-name'));
    await tester.dragUntilVisible(firstName, find.byType(Scrollable).first,
        const Offset(0, 220));
    await tester.pumpAndSettle();
    await tester.enterText(firstName, 'Mpho');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-review-summary')), findsNothing);
  });
}
