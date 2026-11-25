import 'dart:convert';

import 'package:batlokoa/staff_gateway.dart';
import 'package:batlokoa/staff_client_registration_payload.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const account = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee';
const key = 'synthetic-save-key-12345';

void main() {
  test('staged Save Client transport preserves full payload and auth', () async {
    final payload = <String, dynamic>{
      'branch_id': 'verified-branch',
      'first_name': 'Synthetic',
      'national_id': 'SYNTHETIC-NOT-REAL',
      'external_debts': [{'creditor': 'TEST', 'current_balance': '0'}],
      'consent_to_credit_checks': true,
    };
    var count = 0;
    final mock = MockClient((request) async {
      count++;
      expect(request.method, 'POST');
      expect(request.url.toString(),
          'https://batlokoa.example/api/v1/staff/clients/register');
      expect(request.headers['x-csrf-token'], 'verified-proof');
      expect(request.headers['idempotency-key'], key);
      expect(request.headers['cache-control'], 'no-store');
      expect(request.headers['origin'], isNull);
      expect(jsonDecode(request.body), payload);
      return http.Response(jsonEncode({
        'registered': true, 'client_account_id': account, 'replayed': true,
      }), 201);
    });
    final gateway = SameOriginStaffGateway(
      client: mock, origin: Uri.parse('https://batlokoa.example'),
      browserManagedOrigin: true, csrfToken: () => 'verified-proof',
    );
    final response = await gateway.createNewClient(
      completePayload: payload, idempotencyKey: key,
    );
    expect(response.clientAccountId, account);
    expect(response.replayed, true);
    expect(count, 1);
  });

  test('offline full capture travels intact to the same-origin gateway', () async {
    final body = buildNewClientRegistrationPayload(
      branchId: '123e4567-e89b-42d3-a456-426614174111',
      firstName: 'Synthetic', lastName: 'Applicant',
      phone: '59000001', dateOfBirth: '1991-05-01',
      gender: 'female', district: 'Maseru',
      employmentStatus: 'employed',
      nationalId: 'SYNTHETIC-NOT-REAL', passportNumber: '',
      extra: {
        'middle_name': 'Test',
        'employer_name': 'Synthetic employer',
        'existing_loan_total': '500.00',
        'bank_account_holder': 'Synthetic Applicant',
        'bank_account_number': '61234567890',
      },
      choices: {'bank_name': 'FNB', 'bank_account_type': 'savings'},
      monthlyIncome: '6000.00',
      hasExistingLoans: true, salaryAccount: true,
      externalDebts: [
        {'creditor': 'Synthetic lender', 'current_balance': '500.00',
         'installment_amount': '100.00', 'remaining_installments': '5'},
      ],
      profileConsent: true, creditConsent: true,
    );
    var sent = 0;
    final gateway = SameOriginStaffGateway(
      client: MockClient((request) async {
        sent++;
        expect(request.url.path, '/api/v1/staff/clients/register');
        expect(request.headers['x-csrf-token'], 'synthetic-proof');
        expect(request.headers['idempotency-key'], key);
        expect(jsonDecode(request.body), body);
        return http.Response(jsonEncode({
          'registered': true,
          'client_account_id': account,
          'replayed': false,
        }), 201);
      }),
      origin: Uri.parse('https://batlokoa.example'),
      csrfToken: () => 'synthetic-proof',
    );
    final confirmation = await gateway.createNewClient(
      completePayload: body, idempotencyKey: key,
    );
    expect(confirmation.clientAccountId, account);
    expect(confirmation.replayed, false);
    expect(sent, 1);
    expect((body['external_debts'] as List).single['current_balance'], '500.00');
    expect((body['bank_account'] as Map)['account_number'], '61234567890');
  });

  test('unreleased endpoint never confirms registration', () async {
    final gateway = SameOriginStaffGateway(
      client: MockClient((_) async => http.Response(
        jsonEncode({'code': 'NEW_ONLY_REGISTRATION_NOT_RELEASED'}), 503,
      )),
      origin: Uri.parse('https://batlokoa.example'),
      csrfToken: () => 'verified-proof',
    );
    await expectLater(gateway.createNewClient(
      completePayload: {'branch_id': 'verified-branch'},
      idempotencyKey: key,
    ), throwsStateError);
  });

  test('rejects missing CSRF and browser-supplied tenant claims before HTTP', () async {
    var calls = 0;
    final never = MockClient((_) async {
      calls++;
      return http.Response('unexpected', 500);
    });
    final noCsrf = SameOriginStaffGateway(
      client: never, origin: Uri.parse('https://batlokoa.example'),
    );
    await expectLater(noCsrf.createNewClient(
      completePayload: {'branch_id': 'verified-branch'}, idempotencyKey: key,
    ), throwsStateError);
    final gateway = SameOriginStaffGateway(
      client: never, origin: Uri.parse('https://batlokoa.example'),
      csrfToken: () => 'proof',
    );
    await expectLater(gateway.createNewClient(
      completePayload: {
        'branch_id': 'verified-branch', 'company_id': 'spoof',
      }, idempotencyKey: key,
    ), throwsArgumentError);
    await expectLater(gateway.createNewClient(
      completePayload: {'branch_id': 'verified-branch'},
      idempotencyKey: 'short',
    ), throwsArgumentError);
    expect(calls, 0);
  });

  test('malformed or unconfirmed receipts are rejected', () async {
    for (final bad in [
      {'registered': true, 'client_account_id': 'not-a-uuid', 'replayed': false},
      {'registered': false, 'client_account_id': account, 'replayed': false},
      {'registered': true, 'client_account_id': account, 'replayed': 'false'},
    ]) {
      final gateway = SameOriginStaffGateway(
        client: MockClient((_) async => http.Response(jsonEncode(bad), 201)),
        origin: Uri.parse('https://batlokoa.example'),
        csrfToken: () => 'verified-proof',
      );
      await expectLater(gateway.createNewClient(
        completePayload: {'branch_id': 'verified-branch'}, idempotencyKey: key,
      ), throwsFormatException);
    }
  });
}
