import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:batlokoa/staff_gateway.dart';

void main() {
  test('web gateway uses authoritative session and CSRF logout', () async {
    final seen = <http.Request>[];
    final mock = MockClient((request) async {
      seen.add(request);
      switch (request.url.path) {
        case '/api/v1/staff/login':
          return http.Response(jsonEncode({'authenticated': true}), 200);
        case '/api/v1/staff/session':
          return http.Response(jsonEncode({
            'authenticated': true,
            'role': 'LOAN_OFFICER',
            'company_id': 'verified-company',
            'branch_ids': ['verified-branch'],
            'company_wide_scope': false,
          }), 200);
        case '/api/v1/staff/logout':
          if (request.headers['x-csrf-token'] != 'verified-proof') {
            return http.Response('Forbidden', 403);
          }
          return http.Response(jsonEncode({'logged_out': true}), 200);
      }
      return http.Response('Not found', 404);
    });
    final gateway = SameOriginStaffGateway(
      client: mock, origin: Uri.parse('https://batlokoa.example'),
      browserManagedOrigin: true, csrfToken: () => 'verified-proof',
    );
    final user = await gateway.login('59000000', 'password');
    expect(user.role, 'LOAN_OFFICER');
    expect(user.branchIds, ['verified-branch']);
    await gateway.logout();
    expect(seen.map((r) => r.url.path), [
      '/api/v1/staff/login', '/api/v1/staff/session',
      '/api/v1/staff/logout'
    ]);
    expect(seen[0].headers.containsKey('origin'), isFalse);
  });

  test('logout fails closed without CSRF proof', () async {
    final gateway = SameOriginStaffGateway(
      client: MockClient((_) async => http.Response('unexpected', 500)),
      origin: Uri.parse('https://batlokoa.example'),
    );
    await expectLater(gateway.logout(), throwsStateError);
  });

  test('invalid server-supplied staff session is rejected', () {
    expect(() => StaffSession.fromJson({
      'authenticated': false, 'role': 'LOAN_OFFICER',
      'company_id': 'company', 'branch_ids': [],
    }), throwsFormatException);
  });
}
