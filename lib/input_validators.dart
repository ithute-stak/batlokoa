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

  /// Client-side plausibility check only; LoanHub must independently verify
  /// affordability and make all lending decisions.
  static String? monthlyIncome(String? raw) {
    final value = raw?.trim() ?? '';
    if (!RegExp(r'^\\d+(?:\\.\\d{1,2})?
    final value = raw?.trim() ?? '';
    if (value.isEmpty) return 'Reference is required';
    if (value.length > 120) return 'Reference is too long';
    return null;
  }
}
).hasMatch(value)) {
      return 'Enter a monthly income with at most 2 decimal places';
    }
    final amount = double.tryParse(value);
    if (amount == null || !amount.isFinite || amount <= 0 || amount > 1000000) {
      return 'Enter a positive monthly income up to M 1,000,000';
    }
    return null;
  }

  static String? incomeSource(String? raw) {
    final value = raw?.trim() ?? '';
    if (value.isEmpty) return 'Income source is required';
    if (value.length > 120) return 'Income source is too long';
    return null;
  }

  static String? reference(String? raw) {
    final value = raw?.trim() ?? '';
    if (value.isEmpty) return 'Reference is required';
    if (value.length > 120) return 'Reference is too long';
    return null;
  }
}
