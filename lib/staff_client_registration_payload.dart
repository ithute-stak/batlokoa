/// Lossless mapping from Batlokoa's existing five-step capture fields to the
/// reviewed LoanHub FullNewOnlyClientCapture schema. Never persists PII locally.
Map<String, dynamic> buildNewClientRegistrationPayload({
  required String branchId,
  required String firstName,
  required String lastName,
  required String phone,
  required String dateOfBirth,
  required String gender,
  required String district,
  required String employmentStatus,
  required String nationalId,
  required String passportNumber,
  required Map<String, String> extra,
  required Map<String, String> choices,
  required String monthlyIncome,
  required bool hasExistingLoans,
  required bool salaryAccount,
  required List<Map<String, String>> externalDebts,
  required bool profileConsent,
  required bool creditConsent,
}) {
  String? optional(String? value) {
    final trimmed = value?.trim() ?? '';
    return trimmed.isEmpty ? null : trimmed;
  }

  final incomeDayText = optional(extra['income_day']);
  final incomeDay = incomeDayText == null ? null : int.tryParse(incomeDayText);
  if (incomeDayText != null && (incomeDay == null || incomeDay < 1 ||
      incomeDay > 31)) {
    throw const FormatException('Income day must be between 1 and 31');
  }

  final bank = optional(choices['bank_name']);
  final accountNumber = optional(extra['bank_account_number']);
  final accountHolder = optional(extra['bank_account_holder']);
  if (bank == null && (accountNumber != null || accountHolder != null)) {
    throw const FormatException(
        'Bank details must not be silently discarded when bank is cleared');
  }
  if (bank != null && (accountNumber == null || accountHolder == null)) {
    throw const FormatException('Complete bank account details are required');
  }
  if (!hasExistingLoans && externalDebts.isNotEmpty) {
    throw const FormatException('External debts require existing-loan declaration');
  }
  final debts = externalDebts.map((debt) {
    final creditor = optional(debt['creditor']);
    final balance = optional(debt['current_balance']);
    final installment = optional(debt['installment_amount']);
    final remaining = int.tryParse(debt['remaining_installments'] ?? '');
    if (creditor == null || balance == null || installment == null ||
        remaining == null || remaining < 0) {
      throw const FormatException('Incomplete existing debt');
    }
    return <String, dynamic>{
      'creditor': creditor,
      'current_balance': balance,
      'installment_amount': installment,
      'remaining_installments': remaining,
    };
  }).toList(growable: false);

  return <String, dynamic>{
    'branch_id': branchId,
    'first_name': firstName.trim(),
    'middle_name': optional(extra['middle_name']),
    'last_name': lastName.trim(),
    'phone': phone.trim(),
    'date_of_birth': dateOfBirth.trim(),
    'gender': gender.trim(),
    'national_id': optional(nationalId),
    'passport_number': optional(passportNumber),
    'marital_status': optional(choices['marital_status']),
    'nationality': optional(extra['nationality']),
    'district': district.trim(),
    'town_or_village': optional(extra['town_or_village']),
    'physical_address': optional(extra['physical_address']),
    'employment_status': employmentStatus.trim(),
    'employment_type': optional(extra['employment_type']),
    'employer_name': optional(extra['employer_name']),
    'job_title': optional(extra['job_title']),
    'income_day': incomeDay,
    'monthly_income': optional(monthlyIncome),
    'salary_date': optional(extra['salary_date']),
    'has_existing_loans': hasExistingLoans,
    'existing_loan_total': hasExistingLoans
        ? (optional(extra['existing_loan_total']) ?? '0') : '0',
    'external_debts': debts,
    'consent_to_share_profile': profileConsent,
    'consent_to_credit_checks': creditConsent,
    if (bank != null)
      'bank_account': <String, dynamic>{
        'bank_name': bank,
        'account_holder': accountHolder,
        'account_number': accountNumber,
        'account_type': choices['bank_account_type'] ?? 'savings',
        'salary_account': salaryAccount,
      },
  };
}
