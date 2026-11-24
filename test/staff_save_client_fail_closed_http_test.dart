import 'dart:convert';

import 'package:batlokoa/staff_gateway.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// These tests exercise only the staged HTTP adapter. They do not mount a
/// server route, submit real customer details, or enable Save Client in the UI.
void main() {
  const key = 'synthetic-registration-guard-key';
  const accountId = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';

  SameOriginStaffGateway gatewayFor(http.Client client) =>
      SameOriginStaffGateway(
        client: client,
        origin: Uri.parse('https://batlokoa.example'),
        csrfToken: () => 'synthetic-csrf-proof',
      );

  Future<StaffCreatedClientReceipt> submit(
          SameOriginStaffGateway gateway) =>
      gateway.createNewClient(
        completePayload: {'branch_id': 'synthetic-branch'},
        idempotencyKey: key,
      );

  test('rejected, unauthorized and ambiguous HTTP statuses never confirm save',
      () async {
    // A valid-looking receipt in a rejected response must not be trusted.
    final forgedReceipt = jsonEncode({
      'registered': true,
      'client_account_id': accountId,
      'replayed': false,
    });
    for (final status in [200, 202, 204, 400, 401, 403, 404, 409, 422, 429, 500, 502, 504]) {
      var calls = 0;
      final gateway = gatewayFor(MockClient((request) async {
        calls++;
        expect(request.method, 'POST');
        return http.Response(forgedReceipt, status);
      }));
      await expectLater(submit(gateway), throwsStateError,
          reason: 'HTTP $status must never be accepted as a new save');
      expect(calls, 1);
    }
  });

  test('oversized 201 confirmation is rejected before JSON parsing', () async {
    final gateway = gatewayFor(MockClient((_) async =>
        http.Response(' ' * 4097, 201)));
    await expectLater(submit(gateway), throwsStateError);
  });

  test('201 requires a JSON object with a valid authoritative receipt',
      () async {
    for (final body in [
      'null',
      '[]',
      '"confirmed"',
      '{',
      jsonEncode({
        'registered': true,
        'client_account_id': accountId,
        // The server must explicitly distinguish a fresh save from a replay.
      }),
    ]) {
      final gateway = gatewayFor(
          MockClient((_) async => http.Response(body, 201)));
      await expectLater(submit(gateway), throwsFormatException);
    }
  });

  test('server-provided tenant and release claims are never client-authoritative',
      () async {
    var calls = 0;
    final gateway = gatewayFor(MockClient((_) async {
      calls++;
      return http.Response('unexpected', 500);
    }));
    for (final forbiddenField in [
      'company_id',
      'user_id',
      'role',
      'independently_approved_release',
    ]) {
      await expectLater(
        gateway.createNewClient(
          completePayload: {
            'branch_id': 'synthetic-branch',
            forbiddenField: 'attacker-controlled',
          },
          idempotencyKey: key,
        ),
        throwsArgumentError,
      );
    }
    expect(calls, 0, reason: 'Unsafe tenant claims must not reach HTTP');
  });
}
