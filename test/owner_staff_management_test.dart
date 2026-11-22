import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/owner_staff_management_screen.dart';
import 'package:batlokoa/owner_staff_registration_screen.dart';

class FakeOwnerGateway implements OwnerStaffManagementGateway {
  int createCalls = 0;
  @override
  Future<List<Map<String, dynamic>>> ownerBranches() async => [
    {'id': 'branch-test', 'name': 'Maseru'},
  ];
  @override
  Future<List<Map<String, dynamic>>> ownerStaff() async => [
    {'id': 'staff-test', 'name': 'Synthetic Employee',
     'role': 'LOAN_OFFICER', 'active': true, 'verified': false},
  ];
  @override
  Future<String> createStaffAccount(Map<String, dynamic> draft) async {
    createCalls++;
    if (draft['branch_id'] != 'branch-test') throw StateError('Wrong branch');
    return 'created-test-only';
  }
}

void main() {
  testWidgets('owner can see staff and approved branch options', (tester) async {
    final gateway = FakeOwnerGateway();
    const owner = StaffSession(role: 'COMPANY_OWNER',
      companyId: 'company-test', branchIds: [], companyWide: true);
    await tester.pumpWidget(MaterialApp(home:
      OwnerStaffManagementScreen(staff: owner, gateway: gateway)));
    await tester.pumpAndSettle();
    expect(find.text('Your team'), findsOneWidget);
    expect(find.text('Synthetic Employee'), findsOneWidget);
    expect(find.byKey(const Key('owner-open-register-staff')), findsOneWidget);
    expect(find.byKey(const Key('owner-create-staff')), findsNothing);
    await tester.tap(find.byKey(const Key('owner-open-register-staff')));
    await tester.pumpAndSettle();
    expect(find.byType(OwnerStaffRegistrationScreen), findsOneWidget);
    expect(find.byKey(const Key('owner-create-staff')), findsOneWidget);
    expect(gateway.createCalls, 0);
  });

  testWidgets('non-owner never loads another company staff', (tester) async {
    final gateway = FakeOwnerGateway();
    const employee = StaffSession(role: 'BRANCH_MANAGER',
      companyId: 'company-test', branchIds: ['branch-test'], companyWide: false);
    await tester.pumpWidget(MaterialApp(home:
      OwnerStaffManagementScreen(staff: employee, gateway: gateway)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('owner-staff-error')), findsOneWidget);
    expect(find.text('Synthetic Employee'), findsNothing);
    expect(gateway.createCalls, 0);
  });
}
