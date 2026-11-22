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
  final finder = find.byKey(Key('register-$key'));
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.enterText(finder, value);
}

Future<void> next(WidgetTester tester) async {
  tester.testTextInput.hide();
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('register-continue')));
  await tester.pumpAndSettle();
}

Future<void> previous(WidgetTester tester) async {
  await tester.tap(find.text('Previous'));
  await tester.pumpAndSettle();
}

Future<void> prepareValidSteps(WidgetTester tester) async {
  await enter(tester, 'first-name', 'Palesa');
  await enter(tester, 'last-name', 'Mokoena');
  await enter(tester, 'phone', '59000000');
  await next(tester);
  expect(find.text('Identity and address'), findsOneWidget);
  await enter(tester, 'date-of-birth', '1990-01-01');
  await enter(tester, 'district', 'Maseru');
  await enter(tester, 'national-id', 'TEST-NATIONAL-ID');
  await next(tester);
  expect(find.text('Employment and loans'), findsOneWidget);
  await enter(tester, 'monthly-income', '1250.00');
  await next(tester);
  expect(find.text('Banking details'), findsOneWidget);
  await next(tester);
  expect(find.text('Consent and review'), findsOneWidget);
}

void main() {
  testWidgets('five stages match LoanHub and prohibit client creation',
      (tester) async {
    await showForm(tester);
    expect(find.text('Personal details'), findsOneWidget);
    expect(find.text('Step 1 of 5'), findsOneWidget);
    await prepareValidSteps(tester);
    expect(find.text('Step 5 of 5'), findsOneWidget);
    expect(find.text('Submit registration — unavailable'), findsOneWidget);
    final submit = tester.widget<OutlinedButton>(
      find.widgetWithText(OutlinedButton, 'Submit registration — unavailable'));
    expect(submit.onPressed, isNull);
    expect(find.byKey(const Key('register-review-summary')), findsNothing);
    await tester.ensureVisible(find.byKey(const Key('register-review')));
    await tester.tap(find.byKey(const Key('register-review')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-review-summary')), findsOneWidget);
    expect(find.textContaining('Palesa'), findsWidgets);
    expect(find.textContaining('TEST-NATIONAL-ID'), findsNothing);
  });

  testWidgets('required fields prevent moving into the next stage',
      (tester) async {
    await showForm(tester);
    await next(tester);
    expect(find.text('Step 1 of 5'), findsOneWidget);
    expect(find.text('Personal details'), findsOneWidget);
    await enter(tester, 'first-name', 'Palesa');
    await enter(tester, 'last-name', 'Mokoena');
    await enter(tester, 'phone', '59000000');
    await next(tester);
    expect(find.text('Identity and address'), findsOneWidget);
    await enter(tester, 'date-of-birth', '1990-01-01');
    await enter(tester, 'district', 'Maseru');
    await next(tester);
    expect(find.text('Step 2 of 5'), findsOneWidget);
  });

  testWidgets('in-memory draft survives back and forth without saving',
      (tester) async {
    await showForm(tester);
    await enter(tester, 'first-name', 'Mpho');
    await enter(tester, 'last-name', 'Theko');
    await enter(tester, 'phone', '59000001');
    await next(tester);
    await previous(tester);
    final first = tester.widget<TextFormField>(
        find.byKey(const Key('register-first-name')));
    expect(first.controller?.text, 'Mpho');
    expect(find.byKey(const Key('register-review-summary')), findsNothing);
  });

  testWidgets('missing authorized branch cannot enter identity stage',
      (tester) async {
    await showForm(tester, staff: const StaffSession(
      role: 'LOAN_OFFICER', companyId: 'test-company',
      branchIds: [], companyWide: false,
    ));
    expect(find.textContaining('No authorized branch available'), findsOneWidget);
    await enter(tester, 'first-name', 'Palesa');
    await enter(tester, 'last-name', 'Mokoena');
    await enter(tester, 'phone', '59000000');
    await next(tester);
    expect(find.text('Step 1 of 5'), findsOneWidget);
  });
}
