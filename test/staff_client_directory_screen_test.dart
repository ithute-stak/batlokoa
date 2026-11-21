import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_client_directory_screen.dart';

class DirectoryGateway implements StaffGateway {
  List<StaffClient> clients;
  bool fail;
  String? lastBranch;
  String? lastSearch;
  DirectoryGateway({this.clients = const [], this.fail = false});

  @override
  Future<List<StaffClient>> findClients({
    String search = '', String? branchId, int limit = 30,
  }) async {
    lastSearch = search;
    lastBranch = branchId;
    if (fail) throw StateError('Upstream details must never be exposed');
    return clients;
  }

  @override Future<StaffSession?> session() async => null;
  @override Future<StaffSession> login(String phone, String password) async =>
      throw StateError('Not in use');
  @override
  Future<StaffRegistrationPreflight> validateRegistration(
      Map<String, dynamic> draft) async =>
      throw StateError('Preflight disabled in this fixture');
  @override Future<void> logout() async {}
}

const staff = StaffSession(
  role: 'LOAN_OFFICER',
  companyId: 'company-a',
  branchIds: ['branch-a'],
  companyWide: false,
);

void main() {
  testWidgets('branch-scoped search displays minimum client details', (tester) async {
    final gateway = DirectoryGateway(clients: const [
      StaffClient(accountId: 'account-1', accountReference: 'BFS-001',
        companyId: 'company-a', branchId: 'branch-a',
        fullName: 'Synthetic Client', status: 'active'),
    ]);
    await tester.pumpWidget(MaterialApp(home:
      StaffClientDirectoryScreen(gateway: gateway, staff: staff)));
    await tester.pumpAndSettle();
    expect(gateway.lastBranch, 'branch-a');
    expect(find.text('Synthetic Client'), findsOneWidget);
    expect(find.byKey(const Key('staff-client-account-1')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('staff-client-search')), 'Synthetic');
    await tester.tap(find.byKey(const Key('staff-client-search-button')));
    await tester.pumpAndSettle();
    expect(gateway.lastSearch, 'Synthetic');
    await tester.tap(find.byKey(const Key('staff-client-account-1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Loan applications and registration writes'), findsOneWidget);
    expect(find.text('Submit loan'), findsNothing);
  });

  testWidgets('cross-company clients are rejected rather than shown', (tester) async {
    final gateway = DirectoryGateway(clients: const [
      StaffClient(accountId: 'unsafe', accountReference: 'BAD',
        companyId: 'company-b', branchId: 'branch-a',
        fullName: 'Forbidden Person', status: 'active'),
    ]);
    await tester.pumpWidget(MaterialApp(home:
      StaffClientDirectoryScreen(gateway: gateway, staff: staff)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('staff-clients-error')), findsOneWidget);
    expect(find.text('Forbidden Person'), findsNothing);
  });

  testWidgets('upstream errors show generic retry, not internal message', (tester) async {
    final gateway = DirectoryGateway(fail: true);
    await tester.pumpWidget(MaterialApp(home:
      StaffClientDirectoryScreen(gateway: gateway, staff: staff)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('staff-clients-error')), findsOneWidget);
    expect(find.textContaining('Upstream details'), findsNothing);
    expect(find.text('Retry'), findsOneWidget);
  });
}
