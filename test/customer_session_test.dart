import 'package:batlokoa/customer_session.dart';
import 'package:batlokoa/customer_session_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class FakeSessionRepository implements CustomerSessionRepository {
  final bool? result;
  const FakeSessionRepository(this.result);

  @override
  Future<bool> isAuthenticated() async {
    if (result == null) throw const SessionStatusUnavailable();
    return result!;
  }
}

void main() {
  test('disabled repository fails closed', () async {
    await expectLater(
      const DisabledSessionRepository().isAuthenticated(),
      throwsA(isA<SessionStatusUnavailable>()),
    );
  });

  test('read-only session status accepts valid boolean response', () async {
    var calls = 0;
    final client = MockClient((request) async {
      calls++;
      expect(request.method, 'GET');
      expect(request.url.toString(),
          'https://batlokoa.example.test/api/v1/auth/session');
      expect(request.headers.containsKey('Authorization'), isFalse);
      return http.Response('{"authenticated":false}', 200,
          headers: {'content-type': 'application/json'});
    });
    final repository = GatewaySessionRepository(
      origin: Uri.parse('https://batlokoa.example.test'), client: client);
    expect(await repository.isAuthenticated(), isFalse);
    expect(calls, 1);
  });

  test('authenticated status does not expose identity or loan data', () async {
    final client = MockClient((_) async => http.Response(
        '{"authenticated":true}', 200,
        headers: {'content-type': 'application/json'}));
    final repository = GatewaySessionRepository(
      origin: Uri.parse('https://batlokoa.example.test'), client: client);
    expect(await repository.isAuthenticated(), isTrue);
  });

  test('503, 401, malformed payload and extra fields are unavailable', () async {
    for (final response in [
      http.Response('{"code":"AUTH_DISABLED"}', 503,
          headers: {'content-type': 'application/json'}),
      http.Response('unauthorized', 401),
      http.Response('{"authenticated":"true"}', 200,
          headers: {'content-type': 'application/json'}),
      http.Response('{"authenticated":true,"customer_id":"private"}', 200,
          headers: {'content-type': 'application/json'}),
      http.Response('{"authenticated":false}', 200),
      http.Response('{invalid', 200,
          headers: {'content-type': 'application/json'}),
    ]) {
      final repository = GatewaySessionRepository(
        origin: Uri.parse('https://batlokoa.example.test'),
        client: MockClient((_) async => response),
      );
      await expectLater(repository.isAuthenticated(),
          throwsA(isA<SessionStatusUnavailable>()));
    }
  });

  test('only explicitly approved HTTPS origins can be injected', () {
    for (final origin in [
      'http://batlokoa.example.test',
      'https://user:password@batlokoa.example.test',
      'https://batlokoa.example.test/path',
      'https://batlokoa.example.test?query=1',
    ]) {
      expect(
        () => GatewaySessionRepository(
          origin: Uri.parse(origin),
          client: MockClient((_) async => http.Response('', 200)),
        ),
        throwsArgumentError,
      );
    }
  });

  testWidgets('default screen reports unconnected sign-in, never a login',
      (tester) async {
    await tester.pumpWidget(
        const MaterialApp(home: CustomerSessionScreen()));
    await tester.pumpAndSettle();
    expect(find.text('Secure sign-in is not connected in this preview.'),
        findsOneWidget);
    expect(find.textContaining('loan access or payments'), findsOneWidget);
    expect(find.text('Sign in'), findsNothing);
  });

  testWidgets('authenticated status is explicitly not loan authorization',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: CustomerSessionScreen(
          repository: FakeSessionRepository(true)),
    ));
    await tester.pumpAndSettle();
    expect(find.textContaining('Loan account authorization is not confirmed'),
        findsOneWidget);
  });
}
