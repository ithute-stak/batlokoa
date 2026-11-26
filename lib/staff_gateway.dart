import 'dart:convert';
import 'staff_location_capture.dart';
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

/// Optional location-aware login; the server still verifies branch membership.
abstract class StaffLocationLoginGateway {
  Future<StaffSession> loginWithLocation(String phone, String password, {
    String? otp, String? recoveryCode,
    String? branchId, required StaffLocationCapture capture,
  });
}

/// Registration release state from LoanHub; never authorizes a write.
class StaffRegistrationReadiness {
  final bool registrationAvailable;
  final bool canCreateClient;
  final bool requiresIdentityApproval;
  final bool requiresReleaseApproval;

  const StaffRegistrationReadiness({
    required this.registrationAvailable, required this.canCreateClient,
    required this.requiresIdentityApproval, required this.requiresReleaseApproval,
  });

  factory StaffRegistrationReadiness.fromJson(Map<String, dynamic> data) {
    if (data['registration_available'] != false ||
        data['can_create_client'] != false ||
        data['reason_code'] != 'NEW_ONLY_REGISTRATION_NOT_RELEASED' ||
        data['requires_identity_migration_approval'] is! bool ||
        data['requires_independent_release_approval'] is! bool) {
      throw const FormatException('Untrusted LoanHub registration status');
    }
    return StaffRegistrationReadiness(
      registrationAvailable: false, canCreateClient: false,
      requiresIdentityApproval:
          data['requires_identity_migration_approval'] as bool,
      requiresReleaseApproval:
          data['requires_independent_release_approval'] as bool,
    );
  }
}

abstract class StaffRegistrationReadinessGateway {
  Future<StaffRegistrationReadiness> registrationReadiness();
}

/// Independent server-side duplicate screening before any client form step.
/// A no-match is only a candidate, never an authorization to create a client.
class StaffNationalIdCheck {
  final bool mayContinuePreparation;
  final String status;
  const StaffNationalIdCheck({
    required this.mayContinuePreparation, required this.status,
  });

  factory StaffNationalIdCheck.fromJson(Map<String, dynamic> data) {
    final status = data['status'];
    final candidate = data['may_continue_preparation'];
    if ((status != 'existing_or_review' && status != 'candidate_only') ||
        candidate is! bool ||
        candidate != (status == 'candidate_only') ||
        data['registration_authorized'] != false ||
        data['human_review_required'] != true) {
      throw const FormatException('Untrusted identity review response');
    }
    return StaffNationalIdCheck(
      mayContinuePreparation: candidate, status: status as String);
  }
}

abstract class StaffNationalIdGateway {
  Future<StaffNationalIdCheck> checkNationalId({
    required String nationalId, required String branchId,
  });
}

abstract class StaffRegistrationBranchGateway {
  Future<List<Map<String, String>>> registrationBranches();
}

/// Read-only options are sourced from LoanHub, not browser constants.
abstract class StaffRegistrationEmployerGateway {
  Future<List<Map<String, String>>> registrationEmployers();
}

/// Server-confirmed registration receipt, with no client PII.
class StaffCreatedClientReceipt {
  final String clientAccountId;
  final bool replayed;
  const StaffCreatedClientReceipt({
    required this.clientAccountId, required this.replayed,
  });

  factory StaffCreatedClientReceipt.fromJson(Map<String, dynamic> data) {
    final id = data['client_account_id'];
    if (data['registered'] != true || id is! String ||
        !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(id) ||
        data['replayed'] is! bool) {
      throw const FormatException('Untrusted client registration confirmation');
    }
    return StaffCreatedClientReceipt(
      clientAccountId: id, replayed: data['replayed'] as bool,
    );
  }
}

/// Staged transport only. The production Save Client button remains disabled.
abstract class StaffNewClientCreationGateway {
  Future<StaffCreatedClientReceipt> createNewClient({
    required Map<String, dynamic> completePayload,
    required String idempotencyKey,
  });
}

/// Owner-only staff management, separate from client registration.
abstract class OwnerStaffManagementGateway {
  Future<List<Map<String, dynamic>>> ownerBranches();
  Future<List<Map<String, dynamic>>> ownerStaff();
  Future<String> createStaffAccount(Map<String, dynamic> draft);
}

class StaffAttendanceSession {
  final int id;
  final String branchId;
  final DateTime clockedInAt;
  final DateTime? clockedOutAt;
  const StaffAttendanceSession(this.id, this.branchId, this.clockedInAt, this.clockedOutAt);

  factory StaffAttendanceSession.fromJson(Map<String, dynamic> data) {
    final id = data['session_id'];
    final branch = data['branch_id'];
    final start = data['clocked_in_at'];
    final end = data['clocked_out_at'];
    if (id is! int || id <= 0 || branch is! String || branch.isEmpty ||
        start is! String || (end != null && end is! String)) {
      throw const FormatException('Invalid attendance session');
    }
    final opened = DateTime.parse(start);
    final closed = end == null ? null : DateTime.parse(end as String);
    if (!opened.isUtc || (closed != null && (!closed.isUtc || closed.isBefore(opened)))) {
      throw const FormatException('Invalid attendance time');
    }
    return StaffAttendanceSession(id, branch, opened, closed);
  }
}

abstract class StaffAttendanceGateway {
  Future<StaffAttendanceSession?> attendanceStatus();
  Future<List<StaffAttendanceSession>> attendanceHistory({int limit = 30, int? before});
  Future<void> recordAttendance(String branchId, StaffLocationCapture capture, {required bool clockIn});
}

enum StaffPerimeterReading { inside, outside, unverified }

class StaffMonitorReceipt {
  final int sessionId;
  final StaffPerimeterReading reading;
  final StaffPerimeterReading lastConfirmed;
  final DateTime observedAt;
  final bool transitionRecorded;
  const StaffMonitorReceipt(this.sessionId, this.reading, this.lastConfirmed,
      this.observedAt, this.transitionRecorded);
}

abstract class StaffMonitoringGateway {
  Future<StaffMonitorReceipt> submitObservation(
      StaffAttendanceSession session, StaffLocationCapture capture);
}

class OwnerAttendanceAlert {
  final int id;
  final int sessionId;
  final String employeeId;
  final String branchId;
  final String eventType;
  final DateTime observedAt;
  final String? employeeName;
  final String? branchName;
  const OwnerAttendanceAlert(this.id, this.sessionId, this.employeeId,
      this.branchId, this.eventType, this.observedAt,
      {this.employeeName, this.branchName});
}

class OwnerAttendanceAlertPage {
  final List<OwnerAttendanceAlert> alerts;
  final int nextAfter;
  final bool hasMore;
  const OwnerAttendanceAlertPage(this.alerts, this.nextAfter, this.hasMore);
}

abstract class OwnerAttendanceInboxGateway {
  Future<OwnerAttendanceAlertPage> attendanceAlerts({int after = 0, int limit = 50});
}

class OwnerAccessEvent {
  final String id, employeeId, eventType;
  final String? branchId, employeeName, branchName;
  final DateTime observedAt;
  const OwnerAccessEvent(this.id, this.employeeId, this.eventType,
      this.observedAt, {this.branchId, this.employeeName, this.branchName});
}

class OwnerAccessCursor {
  final String observedAt, eventId;
  const OwnerAccessCursor(this.observedAt, this.eventId);
}

class OwnerAccessEventPage {
  final List<OwnerAccessEvent> events;
  final OwnerAccessCursor? nextBefore;
  const OwnerAccessEventPage(this.events, this.nextBefore);
  bool get hasMore => nextBefore != null;
}

abstract class OwnerAccessInboxGateway {
  Future<OwnerAccessEventPage> accessEvents({OwnerAccessCursor? before, int limit = 50});
}

abstract class StaffBranchLocationGateway {
  Future<int> registerBranchLocation(String branchId, StaffLocationCapture capture);
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
class SameOriginStaffGateway implements StaffGateway, StaffSecondFactorGateway, OwnerStaffManagementGateway, StaffNationalIdGateway, StaffRegistrationReadinessGateway, StaffRegistrationEmployerGateway, StaffRegistrationBranchGateway, StaffNewClientCreationGateway, StaffBranchLocationGateway, StaffAttendanceGateway, StaffMonitoringGateway, OwnerAttendanceInboxGateway, StaffLocationLoginGateway, OwnerAccessInboxGateway {
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
  }) => _login(phone, password, otp: otp, recoveryCode: recoveryCode);

  @override
  Future<StaffSession> loginWithLocation(String phone, String password, {
    String? otp, String? recoveryCode,
    String? branchId, required StaffLocationCapture capture,
  }) {
    if ((branchId != null && !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(branchId)) ||
        !capture.isUsableAt(DateTime.now())) {
      throw StateError('Fresh location and valid optional branch required');
    }
    return _login(phone, password, otp: otp, recoveryCode: recoveryCode,
      location: {
        if (branchId != null) 'branch_id': branchId,
        'latitude': capture.latitude,
        'longitude': capture.longitude,
        'accuracy_m': capture.accuracyM,
        'captured_at': capture.capturedAt.toUtc().toIso8601String(),
      });
  }

  Future<StaffSession> _login(String phone, String password, {
    String? otp, String? recoveryCode, Map<String, dynamic>? location,
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
          if (location != null) 'location': location,
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
  Future<List<Map<String, String>>> registrationBranches() async {
    final response = await client.get(
      _url('/api/v1/staff/clients/registration-branches'),
      headers: {'Accept': 'application/json', 'Cache-Control': 'no-store'},
    );
    if (response.statusCode != 200 || response.bodyBytes.length > 131072) {
      throw StateError('LoanHub branch directory unavailable');
    }
    final parsed = jsonDecode(response.body);
    if (parsed is! Map<String, dynamic> ||
        parsed['branches'] is! List || (parsed['branches'] as List).length > 100) {
      throw const FormatException('Invalid registration branches');
    }
    final rows = <Map<String, String>>[];
    final ids = <String>{};
    for (final value in parsed['branches'] as List) {
      if (value is! Map<String, dynamic> || value['id'] is! String ||
          value['name'] is! String) {
        throw const FormatException('Invalid authorized branch');
      }
      final id = value['id'] as String;
      final name = value['name'] as String;
      if (id.isEmpty || name.isEmpty || !ids.add(id)) {
        throw const FormatException('Untrusted branch directory');
      }
      rows.add({'id': id, 'name': name});
    }
    return List<Map<String, String>>.unmodifiable(rows);
  }

  @override
  Future<List<Map<String, String>>> registrationEmployers() async {
    final response = await client.get(
      _url('/api/v1/staff/clients/registration-employers'),
      headers: {'Accept': 'application/json', 'Cache-Control': 'no-store'},
    );
    if (response.statusCode != 200 || response.bodyBytes.length > 131072) {
      throw StateError('LoanHub employer directory unavailable');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> || data['employers'] is! List ||
        (data['employers'] as List).length > 500) {
      throw const FormatException('Invalid employer directory');
    }
    final result = <Map<String, String>>[];
    final seen = <String>{};
    for (final row in data['employers'] as List) {
      if (row is! Map<String, dynamic> || row['id'] is! String ||
          row['code'] is! String || row['name'] is! String) {
        throw const FormatException('Invalid employer option');
      }
      final id = row['id'] as String;
      final code = row['code'] as String;
      final name = row['name'] as String;
      if (id.isEmpty || code.isEmpty || name.isEmpty || !seen.add(id)) {
        throw const FormatException('Duplicate or empty employer option');
      }
      result.add({'id': id, 'code': code, 'name': name});
    }
    return List<Map<String, String>>.unmodifiable(result);
  }

  @override
  Future<StaffRegistrationReadiness> registrationReadiness() async {
    final response = await client.get(
      _url('/api/v1/staff/clients/registration-readiness'),
      headers: {'Accept': 'application/json', 'Cache-Control': 'no-store'},
    );
    if (response.statusCode != 200 || response.bodyBytes.length > 4096) {
      throw StateError('LoanHub registration release status unavailable');
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic>) {
      throw const FormatException('Invalid release status response');
    }
    return StaffRegistrationReadiness.fromJson(body);
  }

  @override
  Future<StaffNationalIdCheck> checkNationalId({
    required String nationalId, required String branchId,
  }) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty) {
      throw StateError('Identity check requires a secure staff session');
    }
    final trimmedId = nationalId.trim();
    if (trimmedId.length < 4 || trimmedId.length > 100 ||
        branchId.trim().isEmpty) {
      throw ArgumentError('Valid national ID and authorized branch required');
    }
    // Never put national ID in a URL, query string, console or browser storage.
    final response = await client.post(
      _url('/api/v1/staff/clients/national-id-check'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cache-Control': 'no-store',
        'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      },
      body: jsonEncode({
        'national_id': trimmedId, 'branch_id': branchId,
      }),
    );
    if (response.statusCode != 200 || response.bodyBytes.length > 2048) {
      throw StateError('Identity screening unavailable or access denied');
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic>) {
      throw const FormatException('Invalid identity screening response');
    }
    return StaffNationalIdCheck.fromJson(body);
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
  Future<StaffCreatedClientReceipt> createNewClient({
    required Map<String, dynamic> completePayload,
    required String idempotencyKey,
  }) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty) {
      throw StateError('Client registration requires secure staff CSRF proof');
    }
    if (!RegExp(r'^[A-Za-z0-9_.-]{16,128}$').hasMatch(idempotencyKey)) {
      throw ArgumentError('Valid registration idempotency key required');
    }
    if (completePayload['branch_id'] is! String ||
        (completePayload['branch_id'] as String).isEmpty ||
        completePayload.containsKey('company_id') ||
        completePayload.containsKey('user_id') ||
        completePayload.containsKey('role') ||
        completePayload.containsKey('independently_approved_release')) {
      throw ArgumentError('Invalid client registration scope');
    }
    final response = await client.post(
      _url('/api/v1/staff/clients/register'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cache-Control': 'no-store',
        'x-csrf-token': csrf,
        'idempotency-key': idempotencyKey,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      },
      body: jsonEncode(completePayload),
    );
    if (response.statusCode == 503) {
      throw StateError('Permanent client registration is not yet released');
    }
    if (response.statusCode != 201 || response.bodyBytes.length > 4096) {
      throw StateError('Client registration was not confirmed by LoanHub');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Unexpected registration confirmation');
    }
    return StaffCreatedClientReceipt.fromJson(data);
  }

  @override
  Future<int> registerBranchLocation(String branchId, StaffLocationCapture capture) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty ||
        !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(branchId) ||
        !capture.isUsableAt(DateTime.now())) {
      throw StateError('Fresh location and secure owner session required');
    }
    final request = http.Request('POST',
        _url('/api/v1/staff/manage/branches/$branchId/location'))
      ..followRedirects = false
      ..headers.addAll({
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cache-Control': 'no-store',
        'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      })
      ..body = jsonEncode(capture.registrationPayload());
    final response = await http.Response.fromStream(await client.send(request));
    if (response.statusCode != 201 || response.bodyBytes.length > 4096) {
      throw StateError('Branch location registration was not confirmed');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> || data['registered'] != true ||
        data['radius_m'] != 10 || data['revision_id'] is! int ||
        (data['revision_id'] as int) <= 0) {
      throw const FormatException('Invalid registration receipt');
    }
    return data['revision_id'] as int;
  }

  Future<Map<String, dynamic>> _attendanceRead(String path, {Map<String, String>? query}) async {
    final uri = _url(path).replace(queryParameters: query);
    final response = await client.get(uri, headers: {
      'Accept': 'application/json', 'Cache-Control': 'no-store',
    });
    if (response.statusCode != 200 || response.bodyBytes.length > 65536) {
      throw StateError('Attendance information unavailable');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Invalid attendance response');
    }
    return data;
  }

  @override
  Future<StaffAttendanceSession?> attendanceStatus() async {
    final data = await _attendanceRead('/api/v1/staff/attendance/status');
    final session = data['session'];
    if (data['clocked_in'] == false && session == null) return null;
    if (data['clocked_in'] != true || session is! Map<String, dynamic>) {
      throw const FormatException('Invalid attendance status');
    }
    final row = StaffAttendanceSession.fromJson(session);
    if (row.clockedOutAt != null) throw const FormatException('Session already closed');
    return row;
  }

  @override
  Future<List<StaffAttendanceSession>> attendanceHistory({int limit = 30, int? before}) async {
    if (limit < 1 || limit > 100 || (before != null && before <= 0)) {
      throw ArgumentError('Invalid attendance pagination');
    }
    final data = await _attendanceRead('/api/v1/staff/attendance/history',
        query: {'limit': '$limit', if (before != null) 'before': '$before'});
    final rows = data['sessions'];
    if (rows is! List || rows.length > limit) {
      throw const FormatException('Invalid attendance history');
    }
    final result = <StaffAttendanceSession>[];
    int? previous = before;
    for (final row in rows) {
      if (row is! Map<String, dynamic>) throw const FormatException('Invalid attendance row');
      final item = StaffAttendanceSession.fromJson(row);
      if (previous != null && item.id >= previous) {
        throw const FormatException('Invalid attendance ordering');
      }
      previous = item.id;
      result.add(item);
    }
    return List<StaffAttendanceSession>.unmodifiable(result);
  }

  @override
  Future<void> recordAttendance(String branchId, StaffLocationCapture capture, {required bool clockIn}) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty || !capture.isUsableAt(DateTime.now()) ||
        !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(branchId)) {
      throw StateError('Fresh precise location and secure staff session required');
    }
    final endpoint = clockIn ? 'clock-in' : 'clock-out';
    final request = http.Request('POST', _url('/api/v1/staff/attendance/$endpoint'))
      ..followRedirects = false
      ..headers.addAll({
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Cache-Control': 'no-store', 'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      })
      ..body = jsonEncode({
        'branch_id': branchId, 'latitude': capture.latitude,
        'longitude': capture.longitude, 'accuracy_m': capture.accuracyM,
        'captured_at': capture.capturedAt.toUtc().toIso8601String(),
      });
    final response = await http.Response.fromStream(await client.send(request));
    if (response.bodyBytes.length > 4096) throw StateError('Attendance not confirmed');
    final data = jsonDecode(response.body);
    if (response.statusCode != 201 || data is! Map<String, dynamic> ||
        data['action'] != (clockIn ? 'clock_in' : 'clock_out') ||
        data['branch_id'] != branchId ||
        data['session_id'] is! int || (data['session_id'] as int) <= 0 ||
        data['event_id'] is! int || (data['event_id'] as int) <= 0) {
      if (data is Map && data['code'] == 'OUTSIDE_PERIMETER') {
        throw StateError('You are outside the authorized office perimeter.');
      }
      throw StateError('Attendance was not confirmed. Refresh status before retrying.');
    }
  }

  @override
  Future<StaffMonitorReceipt> submitObservation(
      StaffAttendanceSession session, StaffLocationCapture capture) async {
    final csrf = csrfToken?.call();
    final age = DateTime.now().difference(capture.capturedAt);
    if (csrf == null || csrf.isEmpty || session.id <= 0 ||
        session.clockedOutAt != null ||
        !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(session.branchId) ||
        !capture.latitude.isFinite || capture.latitude.abs() > 90 ||
        !capture.longitude.isFinite || capture.longitude.abs() > 180 ||
        !capture.accuracyM.isFinite || capture.accuracyM <= 0 ||
        age < const Duration(seconds: -5) || age > const Duration(seconds: 30)) {
      throw StateError('Active session and fresh location required');
    }
    final request = http.Request('POST', _url('/api/v1/staff/attendance/monitor'))
      ..followRedirects = false
      ..headers.addAll({
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Cache-Control': 'no-store', 'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      })
      ..body = jsonEncode({
        'session_id': session.id, 'branch_id': session.branchId,
        'latitude': capture.latitude, 'longitude': capture.longitude,
        'accuracy_m': capture.accuracyM,
        'captured_at': capture.capturedAt.toUtc().toIso8601String(),
      });
    final response = await http.Response.fromStream(await client.send(request));
    if (response.statusCode != 200 || response.bodyBytes.length > 4096) {
      throw StateError('Monitoring observation not confirmed');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> || data['session_id'] is! int ||
        data['session_id'] != session.id || data['observed_at'] is! String ||
        data['transition_recorded'] is! bool) {
      throw const FormatException('Invalid monitoring response');
    }
    StaffPerimeterReading parse(Object? value) {
      switch (value) {
        case 'verified_inside': return StaffPerimeterReading.inside;
        case 'verified_outside': return StaffPerimeterReading.outside;
        case 'unverified': return StaffPerimeterReading.unverified;
        default: throw const FormatException('Invalid perimeter state');
      }
    }
    final reading = parse(data['reading']);
    final confirmed = parse(data['last_confirmed']);
    final observed = DateTime.parse(data['observed_at'] as String);
    final transition = data['transition_recorded'] as bool;
    if (!observed.isUtc || confirmed == StaffPerimeterReading.unverified ||
        (transition && reading != confirmed)) {
      throw const FormatException('Inconsistent monitoring response');
    }
    return StaffMonitorReceipt(session.id, reading, confirmed, observed, transition);
  }

  @override
  Future<OwnerAttendanceAlertPage> attendanceAlerts({int after = 0, int limit = 50}) async {
    if (after < 0 || limit < 1 || limit > 100) {
      throw ArgumentError('Invalid alert pagination');
    }
    final uri = _url('/api/v1/staff/manage/attendance/alerts').replace(
        queryParameters: {'after': '$after', 'limit': '$limit'});
    final request = http.Request('GET', uri)
      ..followRedirects = false
      ..headers.addAll({'Accept': 'application/json', 'Cache-Control': 'no-store'});
    final response = await http.Response.fromStream(await client.send(request));
    if (response.statusCode != 200 || response.bodyBytes.length > 65536) {
      throw StateError('Owner attendance inbox unavailable');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> || data['alerts'] is! List ||
        data['next_after'] is! int || data['has_more'] is! bool) {
      throw const FormatException('Invalid alert page');
    }
    final rows = data['alerts'] as List;
    if (rows.length > limit) throw const FormatException('Oversized alert page');
    final alerts = <OwnerAttendanceAlert>[];
    var previous = after;
    for (final row in rows) {
      if (row is! Map<String, dynamic>) throw const FormatException('Invalid alert');
      final id = row['alert_id'];
      final session = row['session_id'];
      final employee = row['employee_id'];
      final branch = row['branch_id'];
      final event = row['event_type'];
      final observed = row['observed_at'];
      if (id is! int || id <= previous || session is! int || session <= 0 ||
          employee is! String || employee.isEmpty || employee.length > 36 ||
          branch is! String || branch.isEmpty || branch.length > 36 ||
          event is! String ||
          !['reported_outside_perimeter', 'reported_inside_perimeter'].contains(event) ||
          observed is! String) {
        throw const FormatException('Invalid attendance alert');
      }
      final date = DateTime.parse(observed);
      if (!date.isUtc) throw const FormatException('Invalid alert timestamp');
      String? label(Object? value, int maxLength) {
        if (value == null) return null;
        if (value is! String || value.length > maxLength) {
          throw const FormatException('Invalid attendance label');
        }
        final trimmed = value.trim();
        return trimmed.isEmpty ? null : trimmed;
      }
      alerts.add(OwnerAttendanceAlert(id, session, employee, branch, event, date,
          employeeName: label(row['employee_name'], 200),
          branchName: label(row['branch_name'], 120)));
      previous = id;
    }
    if (data['next_after'] != previous ||
        (data['has_more'] == true && rows.length != limit)) {
      throw const FormatException('Invalid alert cursor');
    }
    return OwnerAttendanceAlertPage(List.unmodifiable(alerts), previous, data['has_more'] as bool);
  }

  @override
  Future<OwnerAccessEventPage> accessEvents({OwnerAccessCursor? before, int limit = 50}) async {
    final uuid = RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
    bool validId(Object? value) => value is String && uuid.hasMatch(value);
    if (limit < 1 || limit > 100 ||
        (before != null && (!validId(before.eventId) ||
          DateTime.tryParse(before.observedAt)?.isUtc != true))) {
      throw ArgumentError('Invalid access event pagination');
    }
    final uri = _url('/api/v1/staff/manage/attendance/access-events').replace(
      queryParameters: {'limit': '$limit',
        if (before != null) 'before_at': before.observedAt,
        if (before != null) 'before_id': before.eventId});
    final request = http.Request('GET', uri)
      ..followRedirects = false
      ..headers.addAll({'Accept': 'application/json', 'Cache-Control': 'no-store'});
    final response = await http.Response.fromStream(await client.send(request));
    if (response.statusCode != 200 || response.bodyBytes.length > 131072) {
      throw StateError('Owner access inbox unavailable');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> || data['events'] is! List ||
        data['has_more'] is! bool) {
      throw const FormatException('Invalid access page');
    }
    final rows = data['events'] as List;
    if (rows.length > limit) throw const FormatException('Oversized access page');
    final events = <OwnerAccessEvent>[];
    final seen = <String>{};
    DateTime? previous = before == null ? null : DateTime.parse(before.observedAt);
    String? previousId = before?.eventId;
    String? lastRaw;
    String? label(Object? value, int maxLength) {
      if (value == null) return null;
      if (value is! String || value.length > maxLength) {
        throw const FormatException('Invalid access event label');
      }
      return value.trim().isEmpty ? null : value.trim();
    }
    for (final row in rows) {
      if (row is! Map<String, dynamic>) throw const FormatException('Invalid access event');
      final id = row['event_id'];
      final employee = row['employee_id'];
      final branch = row['branch_id'];
      final kind = row['event_type'];
      final observed = row['observed_at'];
      if (!validId(id) || !validId(employee) ||
          (branch != null && !validId(branch)) ||
          !['reported_login_outside', 'staff_logged_out'].contains(kind) ||
          (kind == 'reported_login_outside' && branch == null) ||
          observed is! String) {
        throw const FormatException('Invalid access event fields');
      }
      final date = DateTime.parse(observed);
      final eventId = id as String;
      if (!date.isUtc || !seen.add(eventId) ||
          (previous != null && (date.isAfter(previous) ||
            (date == previous && eventId.compareTo(previousId!) >= 0)))) {
        throw const FormatException('Invalid access event ordering');
      }
      events.add(OwnerAccessEvent(eventId, employee as String, kind as String,
          date, branchId: branch as String?,
          employeeName: label(row['employee_name'], 200),
          branchName: label(row['branch_name'], 120)));
      previous = date;
      previousId = eventId;
      lastRaw = observed;
    }
    final cursor = data['next_before'];
    OwnerAccessCursor? next;
    if (data['has_more'] == true) {
      if (rows.length != limit || cursor is! Map<String, dynamic> ||
          cursor['event_id'] != previousId || cursor['observed_at'] != lastRaw) {
        throw const FormatException('Invalid access page cursor');
      }
      next = OwnerAccessCursor(lastRaw!, previousId!);
    } else if (cursor != null) {
      throw const FormatException('Unexpected access page cursor');
    }
    return OwnerAccessEventPage(List.unmodifiable(events), next);
  }

  Future<List<Map<String, dynamic>>> _readOwnerList(
      String path, String key) async {
    final response = await client.get(_url(path),
      headers: {'Accept': 'application/json', 'Cache-Control': 'no-store'});
    if (response.statusCode != 200 || response.bodyBytes.length > 262144) {
      throw StateError('Owner staff directory unavailable or access denied');
    }
    final body = jsonDecode(response.body);
    if (body is! Map<String, dynamic> || body[key] is! List) {
      throw const FormatException('Invalid owner staff response');
    }
    final rows = body[key] as List;
    if (rows.length > 100 || rows.any((row) => row is! Map<String, dynamic>)) {
      throw const FormatException('Invalid owner staff list');
    }
    return List<Map<String, dynamic>>.unmodifiable(
      rows.cast<Map<String, dynamic>>());
  }

  @override
  Future<List<Map<String, dynamic>>> ownerBranches() =>
      _readOwnerList('/api/v1/staff/manage/branches', 'branches');

  @override
  Future<List<Map<String, dynamic>>> ownerStaff() =>
      _readOwnerList('/api/v1/staff/manage/members', 'members');

  @override
  Future<String> createStaffAccount(Map<String, dynamic> draft) async {
    final csrf = csrfToken?.call();
    if (csrf == null || csrf.isEmpty) {
      throw StateError('Secure owner action requires CSRF proof');
    }
    final response = await client.post(_url('/api/v1/staff/manage/members'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cache-Control': 'no-store',
        'x-csrf-token': csrf,
        if (!browserManagedOrigin) 'Origin': origin.toString(),
      },
      body: jsonEncode(draft),
    );
    if (response.statusCode == 503) {
      throw StateError('Staff account creation is not yet released.');
    }
    if (response.statusCode == 409) {
      throw StateError('Account already exists or the company staff limit is reached.');
    }
    if (response.statusCode != 201) {
      throw StateError('Staff registration was denied or needs owner verification.');
    }
    final data = jsonDecode(response.body);
    if (data is! Map<String, dynamic> ||
        data['created'] != true || data['staff_id'] is! String) {
      throw const FormatException('Staff registration not confirmed');
    }
    return data['staff_id'] as String;
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
