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
  test('new-client gateway sends CSRF and idempotency; confirms UUID only', () async {
    http.Request? seen;
    final mock = MockClient((request) async {
      seen = request;
      return http.Response(jsonEncode({
        'registered': true,
        'client_account_id': '123e4567-e89b-42d3-a456-426614174000',
        'replayed': false,
      }), 201, headers: {'content-type': 'application/json'});
    });
    final gateway = SameOriginStaffGateway(
      client: mock, origin: Uri.parse('https://batlokoa.example'),
      browserManagedOrigin: true, csrfToken: () => 'verified-proof',
    );
    final receipt = await gateway.createNewClient({
      'branch_id': '123e4567-e89b-42d3-a456-426614174111',
      'first_name': 'Synthetic', 'last_name': 'Applicant',
    }, idempotencyKey: 'synthetic-key-12345');
    expect(receipt.clientAccountId, '123e4567-e89b-42d3-a456-426614174000');
    expect(receipt.replayed, false);
    expect(seen!.url.path, '/api/v1/staff/clients/register');
    expect(seen!.headers['x-csrf-token'], 'verified-proof');
    expect(seen!.headers['idempotency-key'], 'synthetic-key-12345');
    expect(seen!.headers.containsKey('origin'), false);
  });

  test('new-client gateway never reports unreleased HTTP 503 as success', () async {
    final gateway = SameOriginStaffGateway(
      client: MockClient((_) async => http.Response(
          jsonEncode({'code': 'NEW_ONLY_REGISTRATION_NOT_RELEASED'}), 503)),
      origin: Uri.parse('https://batlokoa.example'),
      csrfToken: () => 'verified-proof',
    );
    await expectLater(
      gateway.createNewClient({'branch_id': 'synthetic'},
          idempotencyKey: 'synthetic-key-12345'),
      throwsStateError,
    );
  });

  test('new-client confirmation requires a real UUID and boolean', () {
    const id = '123e4567-e89b-42d3-a456-426614174000';
    expect(() => StaffNewClientReceipt.fromJson({
      'registered': true, 'client_account_id': id, 'replayed': 'false',
    }), throwsFormatException);
    expect(() => StaffNewClientReceipt.fromJson({
      'registered': true, 'client_account_id': 'not-an-account',
      'replayed': false,
    }), throwsFormatException);
    expect(() => StaffNewClientReceipt.fromJson({
      'registered': false, 'client_account_id': id, 'replayed': false,
    }), throwsFormatException);
  });

}
