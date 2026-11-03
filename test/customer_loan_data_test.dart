import 'package:batlokoa/customer_loan_data.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Map<String, dynamic> record({
    Object? amount = 580005,
    Object? currency = 'LSL',
    Object? id = 'loan-123',
  }) => {
    'loan_id': id,
    'status': 'active',
    'outstanding': {'currency': currency, 'minor_units': amount},
  };

  test('parses authorised gateway contract and formats LSL', () {
    final result = parseCustomerLoans({'loans': [record()]});
    expect(result.single.loanId, 'loan-123');
    expect(result.single.outstandingDisplay, 'M 5,800.05');
  });

  test('empty real loan list remains empty', () {
    expect(parseCustomerLoans({'loans': []}), isEmpty);
  });

  test('rejects non-LSL, negative and invalid amounts', () {
    for (final value in [record(currency: 'USD'),
      record(amount: -1), record(amount: 2.5), record(amount: '200'),
      record(amount: 100000000001)]) {
      expect(() => parseCustomerLoans({'loans': [value]}),
        throwsFormatException);
    }
  });

  test('rejects duplicates and malformed envelopes', () {
    expect(() => parseCustomerLoans({'loans': [record(), record()]}),
      throwsFormatException);
    expect(() => parseCustomerLoans({'status': 'ok'}), throwsFormatException);
    expect(() => parseCustomerLoans({'loans': [], 'balance': 500}),
      throwsFormatException);
    expect(() => parseCustomerLoans({'loans': [record(id: '')]}),
      throwsFormatException);
  });

  test('disabled repository never returns fictional loan data', () async {
    await expectLater(const DisabledCustomerLoanRepository().loadMyLoans(),
      throwsA(isA<IntegrationUnavailable>()));
  });
}
