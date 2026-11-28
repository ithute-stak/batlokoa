// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

import 'staff_location_capture.dart';

Future<StaffLocationCapture> captureStaffLocation() async {
  if (Uri.base.scheme != 'https') {
    throw StateError('A secure HTTPS connection is required.');
  }
  final position = await html.window.navigator.geolocation.getCurrentPosition(
    enableHighAccuracy: true,
    maximumAge: Duration.zero,
    timeout: const Duration(seconds: 20),
  );
  final coords = position.coords;
  final latitude = coords?.latitude;
  final longitude = coords?.longitude;
  final accuracy = coords?.accuracy;
  final timestamp = position.timestamp;
  if (latitude == null || longitude == null || accuracy == null ||
      timestamp == null) {
    throw StateError('Location reading is incomplete.');
  }
  final result = StaffLocationCapture(
    latitude: latitude.toDouble(),
    longitude: longitude.toDouble(),
    accuracyM: accuracy.toDouble(),
    capturedAt: DateTime.fromMillisecondsSinceEpoch(timestamp.toInt(), isUtc: true),
  );
  if (!result.isUsableAt(DateTime.now())) {
    throw StateError('Location is stale or not accurate enough. Please retry.');
  }
  return result;
}
