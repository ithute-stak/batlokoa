import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_client_registration_screen.dart';
import 'package:batlokoa/staff_client_directory_screen.dart';

const assigned = StaffSession(
  role: 'LOAN_OFFICER', companyId: 'synthetic-company',
  branchIds: ['synthetic-branch'], companyWide: false,
);

class MockIdentityGateway implements StaffGateway, StaffNationalIdGateway, StaffRegistrationReadinessGateway, StaffRegistrationEmployerGateway {
  bool match;
  bool fail;
  int checks = 0;
  int readinessChecks = 0;
  @override
  Future<List<Map<String, String>>> registrationEmployers() async => [
    {
      'id': '123e4567-e89b-42d3-a456-426614174222',
      'code': 'LMPS',
      'name': 'Synthetic employer group',
    },
  ];

  @override
  Future<StaffRegistrationReadiness> registrationReadiness() async {
    readinessChecks++;
    return const StaffRegistrationReadiness(
      registrationAvailable: false, canCreateClient: false,
      requiresIdentityApproval: true, requiresReleaseApproval: true,
    );
  }
  MockIdentityGateway({this.match = false, this.fail = false});

  @override
  Future<StaffNationalIdCheck> checkNationalId({
    required String nationalId, required String branchId,
  }) async {
    checks++;
    if (fail) throw StateError('Synthetic upstream unavailable');
    if (branchId != 'synthetic-branch') throw StateError('Wrong branch');
    return StaffNationalIdCheck(
      mayContinuePreparation: !match,
      status: match ? 'existing_or_review' : 'candidate_only',
    );
  }

  @override
  Future<StaffSession?> session() async => null;
  @override
  Future<StaffSession> login(String phone, String password) async =>
      throw StateError('Not a sign-in test');
  @override
  Future<void> logout() async {}
  @override
  Future<StaffRegistrationPreflight> validateRegistration(
      Map<String, dynamic> draft) async =>
      throw StateError('Client submission is disabled');
  @override
  Future<List<StaffClient>> findClients({
    String search = '', String? branchId, int limit = 30,
  }) async => [];
}

Future<void> showForm(WidgetTester tester, MockIdentityGateway gateway,
    {StaffSession staff = assigned}) async {
  await tester.pumpWidget(MaterialApp(home: StaffClientRegistrationScreen(
    staff: staff, gateway: gateway,
  )));
  await tester.pumpAndSettle();
}

Future<void> enter(WidgetTester tester, String field, String value) async {
  final finder = find.byKey(Key('register-$field'));
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.enterText(finder, value);
  await tester.pumpAndSettle();
}

Future<void> continueStep(WidgetTester tester) async {
  tester.testTextInput.hide();
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('register-continue')));
  await tester.pumpAndSettle();
}

Future<void> checkId(WidgetTester tester) async {
  await tester.ensureVisible(find.byKey(const Key('register-check-national-id')));
  await tester.tap(find.byKey(const Key('register-check-national-id')));
  await tester.pumpAndSettle();
}

Future<void> unlock(WidgetTester tester, MockIdentityGateway gateway) async {
  await enter(tester, 'national-id', 'SYNTHETIC-NATIONAL-ID');
  await checkId(tester);
  expect(gateway.checks, 1);
  expect(find.textContaining('No matching identity'), findsOneWidget);
  await continueStep(tester);
  expect(find.text('Personal details'), findsOneWidget);
}

void main() {
  testWidgets('mobile keyboard reveals National ID without fixed header/footer',
      (tester) async {
    final gateway = MockIdentityGateway();
    await tester.pumpWidget(MaterialApp(
      home: MediaQuery(
        data: const MediaQueryData(
          size: Size(390, 720),
          viewInsets: EdgeInsets.only(bottom: 390),
        ),
        child: StaffClientRegistrationScreen(staff: assigned, gateway: gateway),
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-national-id')), findsOneWidget);
    expect(find.text('Step 1 of 6'), findsNothing);
    expect(find.byKey(const Key('register-continue')), findsNothing);
    await tester.ensureVisible(find.byKey(const Key('register-national-id')));
    await tester.enterText(
        find.byKey(const Key('register-national-id')), 'SYNTHETIC-ID');
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-national-id')), findsOneWidget);
  });

  testWidgets('National ID is the first input, no name fields shown', (tester) async {
    final gateway = MockIdentityGateway();
    await showForm(tester, gateway);
    expect(find.text('Check National ID'), findsWidgets);
    expect(find.text('Step 1 of 6'), findsOneWidget);
    expect(find.byKey(const Key('register-national-id')), findsOneWidget);
    expect(find.byKey(const Key('register-first-name')), findsNothing);
    expect(find.byKey(const Key('register-branch')), findsNothing);
    final next = tester.widget<FilledButton>(
      find.byKey(const Key('register-continue')));
    expect(next.onPressed, isNull);
    expect(gateway.checks, 0);
  });

  testWidgets('matching ID blocks all later registration steps', (tester) async {
    final gateway = MockIdentityGateway(match: true);
    await showForm(tester, gateway);
    await enter(tester, 'national-id', 'SYNTHETIC-EXISTING-ID');
    await checkId(tester);
    expect(find.textContaining('possible existing identity'), findsOneWidget);
    final next = tester.widget<FilledButton>(
      find.byKey(const Key('register-continue')));
    expect(next.onPressed, isNull);
    expect(find.byKey(const Key('register-first-name')), findsNothing);
    expect(find.byKey(const Key('register-find-existing-client')),
        findsOneWidget);
    // A matched national ID sends the employee into the authorized,
    // read-only client directory rather than a second registration.
    await tester.scrollUntilVisible(
      find.byKey(const Key('register-find-existing-client')), 160,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('register-find-existing-client')));
    await tester.pumpAndSettle();
    expect(find.byType(StaffClientDirectoryScreen), findsOneWidget);
    expect(find.byKey(const Key('register-first-name')), findsNothing);
  });

  testWidgets('unavailable ID check fails closed and cannot proceed', (tester) async {
    final gateway = MockIdentityGateway(fail: true);
    await showForm(tester, gateway);
    await enter(tester, 'national-id', 'SYNTHETIC-ID');
    await checkId(tester);
    expect(find.textContaining('could not be completed'), findsOneWidget);
    expect(tester.widget<FilledButton>(
      find.byKey(const Key('register-continue'))).onPressed, isNull);
  });

  testWidgets('unmatched identity unlocks five LoanHub stages, no submit',
      (tester) async {
    final gateway = MockIdentityGateway();
    await showForm(tester, gateway);
    await unlock(tester, gateway);
    expect(find.text('Step 2 of 6'), findsOneWidget);
    expect(find.byKey(const Key('register-branch')), findsOneWidget);
    expect(find.byKey(const Key('register-find-existing-client')), findsNothing);
    await enter(tester, 'first-name', 'Palesa');
    await enter(tester, 'last-name', 'Mokoena');
    await enter(tester, 'phone', '59000000');
    await continueStep(tester);
    expect(find.text('Identity and address'), findsOneWidget);
    await enter(tester, 'date-of-birth', '1990-01-01');
    await enter(tester, 'district', 'Maseru');
    await continueStep(tester);
    expect(find.text('Employment and loans'), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('register-employment-type')));
    await tester.tap(find.byKey(const Key('register-employment-type')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Government').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('register-employer-group')));
    await tester.tap(find.byKey(const Key('register-employer-group')));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('Synthetic employer group').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-cdas-employee-number')), findsOneWidget);
    await enter(tester, 'monthly-income', '1250.00');
    await continueStep(tester);
    expect(find.text('Banking details'), findsOneWidget);
    await continueStep(tester);
    expect(find.text('Consent and review'), findsOneWidget);
    expect(find.text('Step 6 of 6'), findsOneWidget);
    expect(gateway.readinessChecks, 1);
    await tester.scrollUntilVisible(
      find.byKey(const Key('register-release-readiness')), 160,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('new-client registration is not released'), findsOneWidget);
    expect(find.text('Submit registration — unavailable'), findsOneWidget);
    final submit = tester.widget<OutlinedButton>(
      find.widgetWithText(OutlinedButton, 'Submit registration — unavailable'));
    expect(submit.onPressed, isNull);
    expect(find.textContaining('SYNTHETIC-NATIONAL-ID'), findsNothing);
  });

  testWidgets('editing ID invalidates a previous successful check', (tester) async {
    final gateway = MockIdentityGateway();
    await showForm(tester, gateway);
    await unlock(tester, gateway);
    await tester.tap(find.text('Previous'));
    await tester.pumpAndSettle();
    await enter(tester, 'national-id', 'DIFFERENT-SYNTHETIC-ID');
    expect(tester.widget<FilledButton>(
      find.byKey(const Key('register-continue'))).onPressed, isNull);
    expect(gateway.checks, 1);
    await checkId(tester);
    expect(gateway.checks, 2);
  });

  testWidgets('no registered branch prevents identity screening', (tester) async {
    final gateway = MockIdentityGateway();
    await showForm(tester, gateway, staff: const StaffSession(
      role: 'LOAN_OFFICER', companyId: 'synthetic-company',
      branchIds: [], companyWide: false,
    ));
    expect(find.textContaining('authorized registration branch'), findsOneWidget);
    expect(tester.widget<FilledButton>(
      find.byKey(const Key('register-check-national-id'))).onPressed, isNull);
    expect(gateway.checks, 0);
  });
}
