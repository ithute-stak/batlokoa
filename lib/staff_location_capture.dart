import 'staff_location_capture_stub.dart'
    if (dart.library.html) 'staff_location_capture_web.dart' as platform;

class StaffLocationCapture {
  final double latitude;
  final double longitude;
  final double accuracyM;
  final DateTime capturedAt;

  const StaffLocationCapture({
    required this.latitude,
    required this.longitude,
    required this.accuracyM,
    required this.capturedAt,
  });

  bool isUsableAt(DateTime now) {
    final age = now.difference(capturedAt);
    return latitude.isFinite && latitude >= -90 && latitude <= 90 &&
        longitude.isFinite && longitude >= -180 && longitude <= 180 &&
        accuracyM.isFinite && accuracyM > 0 && accuracyM <= 5 &&
        age >= const Duration(seconds: -5) &&
        age <= const Duration(seconds: 30);
  }

  Map<String, Object> registrationPayload() => {
    'latitude': latitude,
    'longitude': longitude,
    'accuracy_m': accuracyM,
    'captured_at': capturedAt.toUtc().toIso8601String(),
    'confirm': true,
  };
}

/// Explicit user-initiated capture only; never requests background tracking.
Future<StaffLocationCapture> captureStaffLocation() =>
    platform.captureStaffLocation();
