import 'dart:convert';

import 'package:http/http.dart' as http;

/// Read-only session health. This does not authenticate a customer, return
/// personal data, or grant access to LoanHub or any financial operation.
abstract interface class CustomerSessionRepository {
  Future<bool> isAuthenticated();
}

class SessionStatusUnavailable implements Exception {
  const SessionStatusUnavailable();
}

/// Default until an operator approves a same-origin HTTPS staging gateway.
class DisabledSessionRepository implements CustomerSessionRepository {
  const DisabledSessionRepository();

  @override
  Future<bool> isAuthenticated() async {
    throw const SessionStatusUnavailable();
  }
}

/// Explicitly injected, same-origin HTTPS status client.
/// Never accepts bearer tokens, credentials, customer IDs or redirects.
class GatewaySessionRepository implements CustomerSessionRepository {
  final Uri origin;
  final http.Client client;

  GatewaySessionRepository({required this.origin, required this.client}) {
    if (origin.scheme != 'https' ||
        origin.host.isEmpty ||
        origin.userInfo.isNotEmpty ||
        origin.path.isNotEmpty && origin.path != '/' ||
        origin.hasQuery ||
        origin.hasFragment) {
      throw ArgumentError('A trusted HTTPS origin is required');
    }
  }

  @override
  Future<bool> isAuthenticated() async {
    final url = origin.resolve('/api/v1/auth/session');
    try {
      final response = await client.get(
        url,
        headers: const {'Accept': 'application/json'},
      );
      if (response.statusCode != 200 ||
          response.bodyBytes.length > 4096 ||
          !(response.headers['content-type'] ?? '')
              .toLowerCase().contains('application/json')) {
        throw const SessionStatusUnavailable();
      }
      final Object? data = jsonDecode(response.body);
      if (data is! Map<String, dynamic> ||
          data.length != 1 ||
          data['authenticated'] is! bool) {
        throw const SessionStatusUnavailable();
      }
      return data['authenticated'] as bool;
    } catch (_) {
      throw const SessionStatusUnavailable();
    }
  }
}
