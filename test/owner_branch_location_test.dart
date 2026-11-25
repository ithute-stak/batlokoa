import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/owner_branch_location_screen.dart';
import 'package:batlokoa/owner_staff_management_screen.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_location_capture.dart';

const branch = '12345678-1234-1234-1234-123456789abc';
const owner = StaffSession(role: 'COMPANY_OWNER', companyId: 'company-test',
    branchIds: [], companyWide: true);
const employee = StaffSession(role: 'BRANCH_MANAGER', companyId: 'company-test',
    branchIds: [branch], companyWide: false);

class FakeGateway implements OwnerStaffManagementGateway, StaffBranchLocationGateway {
  int reads = 0;
  int writes = 0;
  bool deny = false;
  @override
  Future<List<Map<String, dynamic>>> ownerBranches() async {
    reads++;
    return [{'id': branch, 'name': 'Test branch'}];
  }
  @override
  Future<List<Map<String, dynamic>>> ownerStaff() async => [];
  @override
  Future<String> createStaffAccount(Map<String, dynamic> draft) async =>
      throw UnsupportedError('Not part of this test');
  @override
  Future<int> registerBranchLocation(String branchId, StaffLocationCapture capture) async {
    writes++;
    expect(branchId, branch);
    expect(capture.accuracyM, 2);
    if (deny) throw StateError('Denied');
    return 7;
  }
}

StaffLocationCapture reading({double accuracy = 2}) => StaffLocationCapture(
  latitude: -29.31, longitude: 27.48, accuracyM: accuracy,
  capturedAt: DateTime.now(),
);

Future<void> open(WidgetTester tester, FakeGateway gateway,
    {StaffSession staff = owner, double accuracy = 2}) async {
  await tester.pumpWidget(MaterialApp(home: OwnerBranchLocationScreen(
    staff: staff, directory: gateway, gateway: gateway,
    capture: () async => reading(accuracy: accuracy),
  )));
  await tester.pumpAndSettle();
}

Future<void> capture(WidgetTester tester) async {
  await tester.tap(find.text('Select branch'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Test branch').last);
  await tester.pumpAndSettle();
  final button = find.text('Capture current location');
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('owner must confirm before registration; success requires receipt', (tester) async {
    final gateway = FakeGateway();
    await open(tester, gateway);
    await capture(tester);
    expect(find.text('Reported accuracy: 2.0 m'), findsOneWidget);
    final save = find.widgetWithText(FilledButton, 'Register branch location');
    await tester.ensureVisible(save);
    expect(tester.widget<FilledButton>(save).onPressed, isNull);
    expect(gateway.writes, 0);
    await tester.ensureVisible(find.byType(CheckboxListTile));
    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    await tester.ensureVisible(save);
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(gateway.writes, 1);
    expect(find.text('Branch location registered. Revision 7.'), findsOneWidget);
  });

  testWidgets('inaccurate capture cannot be submitted', (tester) async {
    final gateway = FakeGateway();
    await open(tester, gateway, accuracy: 8);
    await capture(tester);
    expect(find.text('Register branch location'), findsNothing);
    expect(gateway.writes, 0);
  });

  testWidgets('non-owner cannot load directory or register', (tester) async {
    final gateway = FakeGateway();
    await open(tester, gateway, staff: employee);
    expect(find.text('Verified company owner access is required.'), findsOneWidget);
    expect(gateway.reads, 0);
    expect(gateway.writes, 0);
  });

  testWidgets('owner navigation opens branch locations', (tester) async {
    final gateway = FakeGateway();
    await tester.pumpWidget(MaterialApp(home:
        OwnerStaffManagementScreen(staff: owner, gateway: gateway)));
    await tester.pumpAndSettle();
    final entry = find.byKey(const Key('owner-open-branch-locations'));
    await tester.ensureVisible(entry);
    await tester.tap(entry);
    await tester.pumpAndSettle();
    expect(find.byType(OwnerBranchLocationScreen), findsOneWidget);
    expect(gateway.writes, 0);
  });

  test('stale and future readings are rejected', () {
    final now = DateTime.now();
    for (final seconds in [-31, 6]) {
      final sample = StaffLocationCapture(latitude: -29.31, longitude: 27.48,
          accuracyM: 2, capturedAt: now.add(Duration(seconds: seconds)));
      expect(sample.isUsableAt(now), isFalse);
    }
  });
}
