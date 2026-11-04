import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'customer_loan_data.dart';

/// Opt-in contract test adapter for a future Batlokoa customer gateway.
///
/// This is NOT a direct LoanHub client. The read route is aligned with the repository gateway contract, but
/// production browser-session authentication remains unverified. Do not wire this into the default UI
/// without separately approved, server-enforced borrower authorization.
class GatewayCustomerLoanRepository implements CustomerLoanRepository {
  final Uri origin;
  final http.Client client;
  final bool enabled;
  final String approvedPath;

  GatewayCustomerLoanRepository({
    required this.origin,
    required this.client,
    required this.approvedPath,
    this.enabled = false,
  }) {
    if (origin.scheme != 'https' ||
        origin.host.isEmpty ||
        origin.userInfo.isNotEmpty ||
        (origin.path.isNotEmpty && origin.path != '/') ||
        origin.hasQuery ||
        origin.hasFragment ||
        approvedPath != '/api/v1/me/loans') {
      throw ArgumentError('A trusted HTTPS gateway origin and matching route are required');
    }
  }

  @override
  Future<List<CustomerLoan>> loadMyLoans() async {
    if (!enabled) throw const IntegrationUnavailable();
    final request = http.Request('GET', origin.resolve(approvedPath))
      ..followRedirects = false
      ..headers['Accept'] = 'application/json';
    try {
      final response = await client.send(request);
      if (response.statusCode != 200 ||
          response.contentLength != null && response.contentLength! > 65536 ||
          !(response.headers['content-type'] ?? '')
              .toLowerCase().contains('application/json')) {
        throw const IntegrationUnavailable();
      }
      final bytes = BytesBuilder(copy: false);
      await for (final chunk in response.stream) {
        if (bytes.length + chunk.length > 65536) {
          throw const IntegrationUnavailable();
        }
        bytes.add(chunk);
      }
      final Object? decoded = jsonDecode(utf8.decode(bytes.takeBytes()));
      return parseCustomerLoans(decoded);
    } catch (_) {
      throw const IntegrationUnavailable();
    }
  }
}
