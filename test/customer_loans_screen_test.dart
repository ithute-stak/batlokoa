import 'package:batlokoa/customer_loan_data.dart';
import 'package:batlokoa/customer_loans_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class Repository implements CustomerLoanRepository {
  final List<CustomerLoan>? data;
  const Repository(this.data);

  @override
  Future<List<CustomerLoan>> loadMyLoans() async {
    if (data == null) throw const IntegrationUnavailable();
    return data!;
  }
}

void main() {
  testWidgets('default customer loans view never shows demo balance',
    (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CustomerLoansScreen()));
    await tester.pumpAndSettle();
    expect(find.textContaining('not connected'), findsOneWidget);
    expect(find.text('M 5,800.00'), findsNothing);
    expect(find.text('M 2,450.00'), findsNothing);
    expect(find.text('Try again'), findsOneWidget);
  });

  testWidgets('verified loan shows only repository data',
    (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: CustomerLoansScreen(repository: Repository([
        CustomerLoan(loanId: 'loan-1', status: 'active',
          outstandingMinorUnits: 32150),
      ])),
    ));
    await tester.pumpAndSettle();
    expect(find.text('M 321.50'), findsOneWidget);
    expect(find.text('M 5,800.00'), findsNothing);
  });

  testWidgets('empty state is not filled with sample loans', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: CustomerLoansScreen(repository: Repository([])),
    ));
    await tester.pumpAndSettle();
    expect(find.text('No loans found for this account'), findsOneWidget);
    expect(find.text('M 5,800.00'), findsNothing);
  });
}
