import 'package:flutter/material.dart';

import 'customer_loan_data.dart';
import 'ui_states.dart';

/// Separate from the explicitly labelled demo loan screens.
/// Financial data is never replaced by invented sample amounts on error.
class CustomerLoansScreen extends StatefulWidget {
  final CustomerLoanRepository repository;

  const CustomerLoansScreen({
    super.key,
    this.repository = const DisabledCustomerLoanRepository(),
  });

  @override
  State<CustomerLoansScreen> createState() => _CustomerLoansScreenState();
}

class _CustomerLoansScreenState extends State<CustomerLoansScreen> {
  Loadable<List<CustomerLoan>> state = const Loading();

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => state = const Loading());
    try {
      final loans = await widget.repository.loadMyLoans();
      if (!mounted) return;
      setState(() => state = loans.isEmpty ? const Empty() : Loaded(loans));
    } catch (_) {
      if (!mounted) return;
      setState(() => state = const Failed(
        'Customer loan information is not connected. No live balances are available.',
      ));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('My verified loans')),
    body: SafeArea(child: LoadableView<List<CustomerLoan>>(
      state: state,
      emptyTitle: 'No loans found for this account',
      onRetry: _refresh,
      builder: (context, loans) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Loan balances from your authorised account',
            style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          for (final loan in loans)
            Card(child: ListTile(
              title: Text(loan.outstandingDisplay),
              subtitle: Text('Status: ${loan.status}'),
              trailing: const Icon(Icons.chevron_right),
              // Detail and repayment actions will be added after an
              // authenticated, loan-specific LoanHub API is verified.
            )),
          const SizedBox(height: 12),
          const Text(
            'Loan terms, repayment schedules and payment options are not '
            'available in this preview.',
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
    )),
  );
}
