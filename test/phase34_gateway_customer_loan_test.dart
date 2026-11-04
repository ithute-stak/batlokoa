import 'package:batlokoa/customer_loan_data.dart';
import 'package:batlokoa/gateway_customer_loan_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  final origin = Uri.parse('https://batlokoa.example.test');
  GatewayCustomerLoanRepository repository(
    MockClient client, {bool enabled = true, String path = '/api/v1/me/loans'}
  ) => GatewayCustomerLoanRepository(
    origin: origin, client: client, approvedPath: path, enabled: enabled);

  http.Response jsonResponse(String body, [int code = 200]) =>
      http.Response(body, code, headers: {'content-type': 'application/json'});

  test('disabled reader makes no HTTP requests by default', () async {
    var called = false;
    final reader = repository(MockClient((_) async {
      called = true;
      return jsonResponse('{"loans":[]}');
    }), enabled: false);
    await expectLater(reader.loadMyLoans(),
        throwsA(isA<IntegrationUnavailable>()));
    expect(called, isFalse);
  });

  test('valid gateway summary is read-only and sends no caller identity', () async {
    var calls = 0;
    final reader = repository(MockClient((request) async {
      calls++;
      expect(request.method, 'GET');
      expect(request.url.toString(),
          'https://batlokoa.example.test/api/v1/me/loans');
      expect(request.followRedirects, isFalse);
      expect(request.headers['Accept'], 'application/json');
      expect(request.headers.containsKey('Authorization'), isFalse);
      expect(request.headers.containsKey('X-Tenant-Id'), isFalse);
      expect(request.headers.containsKey('X-Customer-Id'), isFalse);
      return jsonResponse(
        '{"loans":[{"loan_id":"loan-1","status":"active",'
        '"outstanding":{"currency":"LSL","minor_units":2599}}]}');
    }));
    final loans = await reader.loadMyLoans();
    expect(calls, 1);
    expect(loans.single.loanId, 'loan-1');
    expect(loans.single.outstandingDisplay, 'M 25.99');
  });

  test('rejects unauthorised, disabled, redirect and server failures', () async {
    for (final status in [301, 302, 401, 403, 404, 429, 500, 503]) {
      final reader = repository(MockClient((_) async =>
          jsonResponse('{"loans":[]}', status)));
      await expectLater(reader.loadMyLoans(),
          throwsA(isA<IntegrationUnavailable>()), reason: '$status');
    }
  });

  test('rejects malformed, unexpected, duplicate and non-LSL data', () async {
    for (final body in [
      'not json',
      '{"loans":[],"customer_id":"untrusted"}',
      '{"loans":[{"loan_id":"x","status":"active",'
          '"outstanding":{"currency":"USD","minor_units":1}}]}',
      '{"loans":[{"loan_id":"x","status":"active",'
          '"outstanding":{"currency":"LSL","minor_units":1}},'
          '{"loan_id":"x","status":"active",'
          '"outstanding":{"currency":"LSL","minor_units":2}}]}',
    ]) {
      final reader = repository(MockClient((_) async => jsonResponse(body)));
      await expectLater(reader.loadMyLoans(),
          throwsA(isA<IntegrationUnavailable>()));
    }
  });

  test('rejects missing content type and oversized responses', () async {
    final cases = [
      http.Response('{"loans":[]}', 200),
      jsonResponse(' ' * 65537),
    ];
    for (final response in cases) {
      final reader = repository(MockClient((_) async => response));
      await expectLater(reader.loadMyLoans(),
          throwsA(isA<IntegrationUnavailable>()));
    }
  });

  test('requires exact reviewed gateway path and a secure origin', () {
    for (final uri in [
      'http://batlokoa.example.test',
      'https://user:pass@batlokoa.example.test',
      'https://batlokoa.example.test/other',
      'https://batlokoa.example.test?tenant=1',
    ]) {
      expect(() => GatewayCustomerLoanRepository(
          origin: Uri.parse(uri),
          client: MockClient((_) async => jsonResponse('{"loans":[]}')),
          approvedPath: '/api/v1/me/loans'), throwsArgumentError);
    }
    expect(() => repository(
      MockClient((_) async => jsonResponse('{"loans":[]}')),
      path: '/api/v1/admin/loans'), throwsArgumentError);
  });
}
