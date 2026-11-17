import 'staff_gateway.dart';
import 'staff_gateway_factory_stub.dart'
    if (dart.library.js_interop) 'staff_gateway_factory_web.dart' as platform;

/// Use browser same-origin credentials only on HTTPS web deployments.
/// Android/iOS stay fail-closed until reviewed native secure-cookie support.
StaffGateway createStaffGateway() => platform.createStaffGateway();
