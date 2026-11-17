import 'dart:convert';
import 'package:http/http.dart' as http;

/// A read-only Batlokoa staff session snapshot. All values are returned by the
/// verified backend, never selected or asserted by the mobile user.
class StaffSession {
  final String role;
  final String companyId;
  final List<String> branchIds;
  final bool companyWide;
  const StaffSession({
    required this.role, required this.companyId,
    required this.branchIds, required this.companyWide,
  });

  factory StaffSession.fromJson(Map<String, dynamic> json) {
    if (json['authenticated'] != true ||
        json['role'] is! String || json['company_id'] is! String ||
        json['branch_ids'] is! List ||
        !(json['branch_ids'] as List).every((e) => e is String)) {
      throw const FormatException('Untrusted employee session response');
    }
    return StaffSession(
      role: json['role'] as String,
      companyId: json['company_id'] as String,
      branchIds: List<String>.unmodifiable(
          (json['branch_ids'] as List).cast<String>()),
      companyWide: json['company_wide_scope'] == true,
    );
  }
}

abstract class StaffGateway {
  Future<StaffSession?> session();
  Future<StaffSession> login(String phone, String password);
  Future<void> logout();
}

/// Explicitly disabled until a reviewed same-origin BFF client is installed.
/// Unlike the legacy customer preview, this never simulates signing in.
class DisabledStaffGateway implements StaffGateway {
  const DisabledStaffGateway();

  @override
  Future<StaffSession?> session() async => null;

  @override
  Future<StaffSession> login(String phone, String password) async =>
      throw StateError('Employee sign-in has not been configured');

  @override
  Future<void> logout() async {}
}

/// Browser-compatible session gateway. Must be used on the approved HTTPS
/// Batlokoa origin; never transmit credentials to an arbitrary URL.
class SameOriginStaffGateway implements StaffGateway {
  final http.Client client;
  final Uri origin;
  final String? Function()? csrfToken;
  final bool browserManagedOrigin;
  SameOriginStaffGateway({required this.client, required this.origin,
      this.csrfToken, this.browserManagedOrigin = false}) {
    if (origin.scheme != 'https' || origin.host.isEmpty ||
        origin.path.isNotEmpty || origin.hasQuery ||
        origin.hasFragment || origin.userInfo.isNotEmpty) {
      throw ArgumentError('Approved HTTPS origin is required');
    }
  }

  Uri _url(String path) => origin.resolve(path);

  @override
  Future<StaffSession?> session() async {
    final res = await client.get(_url('/api/v1/staff/session'),
        headers: {'Accept': 'application/json'});
    if (res.statusCode == 401 || res.statusCode == 503) return null;
    if (res.statusCode != 200) throw StateError('Session unavailable');
    return StaffSession.fromJson(
        jsonDecode(res.body) as Map<String, dynamic>);
  }

  @override
  Future<StaffSession> login(String phone, String password) async {
    final res = await client.post(_url('/api/v1/staff/login'),
        headers: {'Content-Type': 'application/json',
                  'Accept': 'application/json',
                  if (!browserManagedOrigin) 'Origin': origin.toString()},
        body: jsonEncode({'phone': phone, 'password': password}));
    if (res.statusCode != 200) throw StateError('Employee sign-in was denied');
    // Login response is not sufficient authorization: revalidate via session.
    final verified = await session();
    if (verified == null) throw StateError('Employee session unavailable');
    return verified;
  }

  @override
  Future<void> logout() async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty) {
      throw StateError('Secure employee sign-out requires CSRF proof');
    }
    final res = await client.post(_url('/api/v1/staff/logout'),
        headers: {
          'Accept': 'application/json',
          'x-csrf-token': csrf,
          if (!browserManagedOrigin) 'Origin': origin.toString(),
        });
    if (res.statusCode != 200) {
      throw StateError('Employee sign-out failed');
    }
    final body = jsonDecode(res.body);
    if (body is! Map<String, dynamic> || body['logged_out'] != true) {
      throw StateError('Employee sign-out was not confirmed');
    }
  }
}
