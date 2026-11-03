/// UI-only validation. The backend must validate money as integer minor units.
class DemoInputValidator {
  const DemoInputValidator._();

  static String? amount(String? raw) {
    final value = raw?.trim() ?? '';
    if (!RegExp(r'^\d+(?:\.\d{1,2})?$').hasMatch(value)) {
      return 'Enter an amount with at most 2 decimal places';
    }
    final parsed = double.tryParse(value);
    if (parsed == null || !parsed.isFinite || parsed <= 0 || parsed > 1000000) {
      return 'Enter a positive amount up to M 1,000,000';
    }
    return null;
  }

  static String? reference(String? raw) {
    final value = raw?.trim() ?? '';
    if (value.isEmpty) return 'Reference is required';
    if (value.length > 120) return 'Reference is too long';
    return null;
  }
}
