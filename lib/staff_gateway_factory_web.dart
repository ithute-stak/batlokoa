// Web-only: browser maintains HttpOnly BFF cookies; Dart never reads them.
// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

import 'package:http/browser_client.dart';

import 'staff_gateway.dart';

String? _csrfToken() {
  final raw = html.document.cookie ?? '';
  for (final entry in raw.split(';')) {
    final trimmed = entry.trim();
    const prefix = '__Host-batlokoa_staff_csrf=';
    if (trimmed.startsWith(prefix)) {
      final value = Uri.decodeComponent(trimmed.substring(prefix.length));
      return value.isEmpty ? null : value;
    }
  }
  return null;
}

StaffGateway createStaffGateway() {
  final url = Uri.base;
  if (url.scheme != 'https' || url.host.isEmpty || url.userInfo.isNotEmpty) {
    return const DisabledStaffGateway();
  }
  final origin = Uri(
    scheme: 'https', host: url.host,
    port: url.hasPort ? url.port : null,
  );
  final client = BrowserClient()..withCredentials = true;
  // Browser generates Origin on cross-protection POST requests; do not forge
  // the forbidden Origin header from JavaScript.
  return SameOriginStaffGateway(
    client: client, origin: origin, browserManagedOrigin: true,
    csrfToken: _csrfToken,
  );
}
