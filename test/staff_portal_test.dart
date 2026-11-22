import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_portal.dart';
import 'package:batlokoa/batlokoa_logo.dart';

class FakeStaffGateway implements StaffGateway {
  StaffSession? current;
  bool allowLogin;
  FakeStaffGateway({this.current, this.allowLogin = true});
  @override Future<StaffSession?> session() async => current;
  @override Future<StaffSession> login(String phone, String password) async {
    if (!allowLogin) throw StateError('Denied');
    return current = const StaffSession(
        role: 'LOAN_OFFICER', companyId: 'verified-company',
        branchIds: ['verified-branch'], companyWide: false);
  }
  @override
  Future<StaffRegistrationPreflight> validateRegistration(
      Map<String, dynamic> draft) async =>
      throw StateError('Preflight disabled in this fixture');
  @override Future<void> logout() async { current = null; }
  @override Future<List<StaffClient>> findClients({String search = '', String? branchId, int limit = 30}) async => const [];

}

void main() {
  testWidgets('staff login uses actual gateway and shows verified branch',
      (tester) async {
    final gateway = FakeStaffGateway();
    await tester.pumpWidget(MaterialApp(home: StaffPortal(gateway: gateway)));
    await tester.pumpAndSettle();
    expect(find.text('Employee sign in'), findsOneWidget);
    expect(find.text('Batlokoa Financial Services'), findsWidgets);
    expect(find.byType(BatlokoaLogo), findsWidgets);
    expect(find.text('We make Your Debt Affordable.'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('staff-phone')), '59000000');
    await tester.enterText(find.byKey(const Key('staff-password')), 'secretpass');
    await tester.ensureVisible(find.byKey(const Key('staff-login')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('staff-login')));
    await tester.pumpAndSettle();
    expect(find.text('Employee workspace'), findsOneWidget);
    expect(find.text('Register client'), findsOneWidget);
    expect(find.byKey(const Key('staff-bottom-navigation')), findsOneWidget);
    await tester.tap(find.text('Account').last);
    await tester.pumpAndSettle();
    expect(find.text('Branch ID: verified-branch'), findsOneWidget);
    expect(find.byKey(const Key('staff-find-clients')), findsOneWidget);
    await tester.ensureVisible(find.byKey(const Key('staff-logout')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('staff-logout')));
    await tester.pumpAndSettle();
    expect(find.text('Employee sign in'), findsOneWidget);
  });

  testWidgets('disabled gateway cannot fake employee login', (tester) async {
    await tester.pumpWidget(
        const MaterialApp(home: StaffPortal()));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('staff-phone')), '59000000');
    await tester.enterText(find.byKey(const Key('staff-password')), 'secretpass');
    await tester.ensureVisible(find.byKey(const Key('staff-login')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('staff-login')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('staff-error')), findsOneWidget);
    expect(find.text('Employee workspace'), findsNothing);
  });
  testWidgets('verified company owner receives owner workspace and company scope',
      (tester) async {
    final gateway = FakeStaffGateway(current: const StaffSession(
      role: 'COMPANY_OWNER',
      companyId: 'trusted-company',
      branchIds: [],
      companyWide: true,
    ));
    await tester.pumpWidget(MaterialApp(home: StaffPortal(gateway: gateway)));
    await tester.pumpAndSettle();
    expect(find.text('Company owner workspace'), findsOneWidget);
    expect(find.text('Company-wide staff scope'), findsWidgets);
    expect(find.byKey(const Key('staff-bottom-navigation')), findsOneWidget);
    expect(find.textContaining('Financial approvals and client creation are not enabled'),
        findsOneWidget);
    expect(find.byKey(const Key('staff-find-clients')), findsOneWidget);
  });

}
