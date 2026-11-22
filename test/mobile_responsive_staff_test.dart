import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/batlokoa_design.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_workspace_shell.dart';
import 'package:batlokoa/owner_staff_management_screen.dart';
import 'package:batlokoa/owner_staff_registration_screen.dart';

class ResponsiveOwnerGateway implements StaffGateway, OwnerStaffManagementGateway {
  @override
  Future<StaffSession?> session() async => null;
  @override
  Future<StaffSession> login(String phone, String password) async =>
      throw StateError('Synthetic test does not sign in');
  @override
  Future<void> logout() async {}
  @override
  Future<List<StaffClient>> findClients({
    String search = '', String? branchId, int limit = 30,
  }) async => [];
  @override
  Future<StaffRegistrationPreflight> validateRegistration(
      Map<String, dynamic> draft) async =>
      throw StateError('Not released');
  @override
  Future<List<Map<String, dynamic>>> ownerBranches() async => [
    {'id': 'branch-maseru', 'name': 'Maseru'},
  ];
  @override
  Future<List<Map<String, dynamic>>> ownerStaff() async => [
    {'id': 'staff-one', 'name': 'Synthetic Mobile Employee',
      'role': 'LOAN_OFFICER', 'active': true, 'verified': false},
  ];
  @override
  Future<String> createStaffAccount(Map<String, dynamic> draft) async =>
      throw StateError('Not released');
}

const owner = StaffSession(
  role: 'COMPANY_OWNER', companyId: 'synthetic-company',
  branchIds: [], companyWide: true,
);

Widget fixture(Widget home, double scale) => MaterialApp(
  theme: BatlokoaDesign.theme(),
  builder: (context, child) {
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(scale)),
      child: child!,
    );
  },
  home: home,
);

void setViewport(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
}

void main() {
  const sizes = <Size>[
    Size(320, 640),
    Size(360, 740),
    Size(390, 844),
    Size(430, 932),
    Size(768, 1024),
    Size(1024, 768),
    Size(740, 360),
  ];

  for (final size in sizes) {
    for (final scale in [1.0, 1.8]) {
      testWidgets('owner workspace fits ${size.width}x${size.height} at ${scale}x text',
          (tester) async {
        setViewport(tester, size);
        final gateway = ResponsiveOwnerGateway();
        await tester.pumpWidget(fixture(
          StaffWorkspaceShell(
            session: owner, gateway: gateway,
            onLogout: () async {}, busy: false),
          scale,
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        expect(find.text('Welcome back'), findsOneWidget);
        if (size.width < 820) {
          expect(find.byKey(const Key('staff-bottom-navigation')), findsOneWidget);
        } else {
          expect(find.byType(NavigationRail), findsOneWidget);
        }
        // Verify all tabs are usable, not merely rendered.
        if (size.width < 820) {
          await tester.tap(find.text('Clients').last);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          await tester.tap(find.text('Team').last);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          await tester.tap(find.text('Account').last);
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
        }
      });
    }
  }

  for (final size in [const Size(320, 640), const Size(390, 844)]) {
    testWidgets('owner employee directory works on a ${size.width}px phone',
        (tester) async {
      setViewport(tester, size);
      final gateway = ResponsiveOwnerGateway();
      await tester.pumpWidget(fixture(
        OwnerStaffManagementScreen(staff: owner, gateway: gateway), 1.6));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.scrollUntilVisible(
        find.text('Synthetic Mobile Employee'),
        180,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Synthetic Mobile Employee'), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('owner-open-register-staff')));
      await tester.tap(find.byKey(const Key('owner-open-register-staff')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byType(OwnerStaffRegistrationScreen), findsOneWidget);
      await tester.scrollUntilVisible(
        find.byKey(const Key('staff-first-name')),
        150,
        scrollable: find.byType(Scrollable).last,
      );
      expect(find.byKey(const Key('staff-first-name')), findsOneWidget);
      await tester.scrollUntilVisible(
        find.byKey(const Key('staff-role')),
        160,
        scrollable: find.byType(Scrollable).last,
      );
      expect(find.byKey(const Key('staff-role')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
