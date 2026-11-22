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

/// Minimal directory row, containing no borrower identity documents or balances.
class StaffClient {
  final String accountId;
  final String accountReference;
  final String companyId;
  final String? branchId;
  final String fullName;
  final String status;

  const StaffClient({
    required this.accountId,
    required this.accountReference,
    required this.companyId,
    required this.branchId,
    required this.fullName,
    required this.status,
  });

  factory StaffClient.fromJson(Map<String, dynamic> json) {
    String requiredValue(String key) {
      final value = json[key];
      if (value is! String || value.trim().isEmpty || value.length > 200) {
        throw const FormatException('Invalid client directory response');
      }
      return value;
    }
    final branch = json['branch_id'];
    if (branch != null && (branch is! String || branch.isEmpty)) {
      throw const FormatException('Invalid client branch');
    }
    return StaffClient(
      accountId: requiredValue('account_id'),
      accountReference: requiredValue('account_reference'),
      companyId: requiredValue('company_id'),
      branchId: branch as String?,
      fullName: requiredValue('full_name'),
      status: requiredValue('status'),
    );
  }
}

/// Review only. This deliberately cannot grant permission to submit a client.
class StaffRegistrationPreflight {
  final bool identityReviewRequired;
  final String branchId;
  final List<String> reasons;

  const StaffRegistrationPreflight({
    required this.identityReviewRequired,
    required this.branchId,
    required this.reasons,
  });

  factory StaffRegistrationPreflight.fromJson(Map<String, dynamic> json) {
    if (json['validated'] != true ||
        json['can_submit'] != false ||
        json['identity_review_required'] != true ||
        json['branch_id'] is! String ||
        json['reasons'] is! List ||
        !(json['reasons'] as List).every((v) => v is String)) {
      throw const FormatException('Untrusted registration preflight response');
    }
    return StaffRegistrationPreflight(
      identityReviewRequired: true,
      branchId: json['branch_id'] as String,
      reasons: List<String>.unmodifiable((json['reasons'] as List).cast<String>()),
    );
  }
}

abstract class StaffGateway {
  Future<StaffSession?> session();
  Future<StaffSession> login(String phone, String password);
  Future<void> logout();
  Future<StaffRegistrationPreflight> validateRegistration(Map<String, dynamic> draft);
  Future<List<StaffClient>> findClients({String search = '', String? branchId, int limit = 30});
}

/// Optional extension for LoanHub employees with second-factor verification.
/// Existing staff gateway implementations remain compatible.
abstract class StaffSecondFactorGateway {
  Future<StaffSession> loginWithSecondFactor(
    String phone,
    String password, {
    String? otp,
    String? recoveryCode,
  });
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
  Future<StaffRegistrationPreflight> validateRegistration(Map<String, dynamic> draft) async =>
      throw StateError('Registration preflight is not configured');

  @override
  Future<void> logout() async {}

  @override
  Future<List<StaffClient>> findClients({String search = '', String? branchId, int limit = 30}) async =>
      throw StateError('Employee client directory is not configured');
}

/// Browser-compatible session gateway. Must be used on the approved HTTPS
/// Batlokoa origin; never transmit credentials to an arbitrary URL.
class SameOriginStaffGateway implements StaffGateway, StaffSecondFactorGateway {
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
  Future<StaffSession> login(String phone, String password) =>
      loginWithSecondFactor(phone, password);

  @override
  Future<StaffSession> loginWithSecondFactor(
    String phone,
    String password, {
    String? otp,
    String? recoveryCode,
  }) async {
    if (otp != null && recoveryCode != null) {
      throw ArgumentError('Select either an authenticator code or recovery code');
    }
    final res = await client.post(_url('/api/v1/staff/login'),
        headers: {'Content-Type': 'application/json',
                  'Accept': 'application/json',
                  if (!browserManagedOrigin) 'Origin': origin.toString()},
        body: jsonEncode({
          'phone': phone,
          'password': password,
          if (otp != null) 'otp': otp,
          if (recoveryCode != null) 'recovery_code': recoveryCode,
        }));
    if (res.statusCode != 200) throw StateError('Employee sign-in was denied');
    // Login response is not sufficient authorization: revalidate via session.
    final verified = await session();
    if (verified == null) throw StateError('Employee session unavailable');
    return verified;
  }

  @override
  Future<List<StaffClient>> findClients({
    String search = '', String? branchId, int limit = 30,
  }) async {
    if (search.length > 120 || limit < 1 || limit > 100 ||
        (branchId != null && branchId.trim().isEmpty)) {
      throw ArgumentError('Invalid client directory filters');
    }
    final query = <String, String>{
      'search': search.trim(),
      'limit': '$limit',
      if (branchId != null) 'branch_id': branchId,
    };
    final uri = _url('/api/v1/staff/clients')
        .replace(queryParameters: query);
    final res = await client.get(uri, headers: {
      'Accept': 'application/json',
      'Cache-Control': 'no-store',
    });
    if (res.statusCode == 401) {
      throw StateError('Employee session expired. Sign in again.');
    }
    if (res.statusCode != 200 || res.bodyBytes.length > 262144) {
      throw StateError('Client directory is unavailable');
    }
    final parsed = jsonDecode(res.body);
    if (parsed is! Map<String, dynamic> ||
        parsed['clients'] is! List ||
        (parsed['clients'] as List).length > limit) {
      throw const FormatException('Unexpected client directory response');
    }
    final clients = <StaffClient>[];
    final seen = <String>{};
    for (final item in parsed['clients'] as List) {
      if (item is! Map<String, dynamic>) {
        throw const FormatException('Unexpected client directory record');
      }
      final row = StaffClient.fromJson(item);
      if (!seen.add(row.accountId)) {
        throw const FormatException('Duplicate client directory record');
      }
      clients.add(row);
    }
    return List<StaffClient>.unmodifiable(clients);
  }

  @override
  Future<StaffRegistrationPreflight> validateRegistration(
      Map<String, dynamic> draft) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty) {
      throw StateError('Registration validation requires CSRF proof');
    }
    final response = await client.post(
      _url('/api/v1/staff/clients/registration-preflight'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cache-Control': 'no-store',
        'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      },
      body: jsonEncode(draft),
    );
    if (response.statusCode != 200 || response.bodyBytes.length > 16384) {
      throw StateError('Registration validation unavailable or denied');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Unexpected preflight response');
    }
    return StaffRegistrationPreflight.fromJson(data);
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
