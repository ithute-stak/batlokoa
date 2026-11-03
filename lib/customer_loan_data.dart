/// Batlokoa customer-loan gateway response models.
 ///
 /// This parser accepts only validated summaries returned by the Batlokoa
 /// backend. It is deliberately not a LoanHub admin API client.
class CustomerLoan {
  final String loanId;
  final String status;
  final int outstandingMinorUnits;

  const CustomerLoan({
    required this.loanId,
    required this.status,
    required this.outstandingMinorUnits,
  });

  factory CustomerLoan.fromJson(Object? input) {
    if (input is! Map<String, dynamic>) {
      throw const FormatException('Invalid loan record');
    }
    final id = input['loan_id'];
    final status = input['status'];
    final money = input['outstanding'];
    if (id is! String || id.isEmpty || id.length > 120 ||
        status is! String || status.isEmpty || status.length > 40 ||
        money is! Map<String, dynamic> ||
        money['currency'] != 'LSL' ||
        money['minor_units'] is! int ||
        (money['minor_units'] as int) < 0 ||
        (money['minor_units'] as int) > 100000000000) {
      throw const FormatException('Invalid loan record');
    }
    return CustomerLoan(
      loanId: id,
      status: status,
      outstandingMinorUnits: money['minor_units'] as int,
    );
  }

  String get outstandingDisplay {
    final whole = outstandingMinorUnits ~/ 100;
    final cents = (outstandingMinorUnits % 100).toString().padLeft(2, '0');
    final formatted = whole.toString().replaceAllMapped(
      RegExp(r'\B(?=(\d{3})+(?!\d))'), (match) => ',',
    );
    return 'M $formatted.$cents';
  }
}

List<CustomerLoan> parseCustomerLoans(Object? input) {
  if (input is! Map<String, dynamic> || input.length != 1 ||
      input['loans'] is! List) {
    throw const FormatException('Invalid customer-loan response');
  }
  final values = input['loans'] as List<dynamic>;
  if (values.length > 100) {
    throw const FormatException('Loan response too large');
  }
  final loans = values.map(CustomerLoan.fromJson).toList(growable: false);
  final ids = loans.map((loan) => loan.loanId).toSet();
  if (ids.length != loans.length) {
    throw const FormatException('Duplicate loans');
  }
  return loans;
}

/// A repository contract with NO implicit access to customer credentials.
/// Production implementation requires an approved BFF session and same-origin
/// customer endpoint. Do not put provider bearer tokens in a Flutter bundle.
abstract interface class CustomerLoanRepository {
  Future<List<CustomerLoan>> loadMyLoans();
}

class IntegrationUnavailable implements Exception {
  const IntegrationUnavailable();
}

class DisabledCustomerLoanRepository implements CustomerLoanRepository {
  const DisabledCustomerLoanRepository();

  @override
  Future<List<CustomerLoan>> loadMyLoans() async {
    throw const IntegrationUnavailable();
  }
}
