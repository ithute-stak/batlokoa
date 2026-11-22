import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/staff_client_registration_payload.dart';

Map<String, dynamic> build({
  bool loans = false,
  String bank = '',
  List<Map<String, String>> debts = const [],
}) => buildNewClientRegistrationPayload(
  branchId: '123e4567-e89b-42d3-a456-426614174111',
  firstName: 'Synthetic',
  lastName: 'Client',
  phone: '59000001',
  dateOfBirth: '1991-05-01',
  gender: 'female',
  district: 'Maseru',
  employmentStatus: 'employed',
  nationalId: 'TEST-ONLY-NOT-REAL',
  passportNumber: '',
  extra: {
    'middle_name': 'Test',
    'employer_name': 'Synthetic employer',
    'physical_address': 'Synthetic address',
    'income_day': '25',
    'existing_loan_total': '500.00',
    'bank_account_holder': 'Synthetic Client',
    'bank_account_number': '1234567890',
    'town_or_village': 'Maseru West',
  },
  choices: {
    'marital_status': 'single',
    'bank_name': bank,
    'bank_account_type': 'savings',
  },
  monthlyIncome: '6000.00',
  hasExistingLoans: loans,
  salaryAccount: true,
  externalDebts: debts,
  profileConsent: true,
  creditConsent: false,
);

void main() {
  test('full client mapping retains personal, employment, consents and branch', () {
    final result = build();
    expect(result['first_name'], 'Synthetic');
    expect(result['middle_name'], 'Test');
    expect(result['physical_address'], 'Synthetic address');
    expect(result['employer_name'], 'Synthetic employer');
    expect(result['income_day'], 25);
    expect(result['monthly_income'], '6000.00');
    expect(result['branch_id'], '123e4567-e89b-42d3-a456-426614174111');
    expect(result['consent_to_share_profile'], true);
    expect(result['consent_to_credit_checks'], false);
    expect(result['external_debts'], isEmpty);
    expect(result.containsKey('bank_account'), false);
  });

  test('full client mapping preserves declared external debt and bank', () {
    final result = build(
      loans: true,
      bank: 'NB',
      debts: [
        {'creditor': 'Synthetic lender', 'current_balance': '500.00',
         'installment_amount': '100.00', 'remaining_installments': '5'},
      ],
    );
    expect(result['has_existing_loans'], true);
    expect(result['existing_loan_total'], '500.00');
    final debt = (result['external_debts'] as List).single as Map;
    expect(debt['creditor'], 'Synthetic lender');
    expect(debt['remaining_installments'], 5);
    final bank = result['bank_account'] as Map;
    expect(bank['bank_name'], 'NB');
    expect(bank['account_number'], '1234567890');
    expect(bank['salary_account'], true);
  });

  test('invalid bank and contradictory debt capture cannot be silently dropped', () {
    expect(() => build(bank: 'NB', debts: const []), returnsNormally);
    expect(() => build(debts: [
      {'creditor': 'Synthetic lender', 'current_balance': '500',
       'installment_amount': '100', 'remaining_installments': '5'},
    ]), throwsFormatException);
    expect(() => build(loans: true, debts: [
      {'creditor': 'Synthetic lender', 'current_balance': '500',
       'installment_amount': '100', 'remaining_installments': 'unknown'},
    ]), throwsFormatException);
  });
}
