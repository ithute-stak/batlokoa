import 'package:flutter/material.dart';

/// Fixture-only activity model. Replace with a typed, authenticated IthutePay API
/// response before any production financial activity is shown.
class DemoActivity {
  final String id;
  final String title;
  final String date;
  final String amount;
  final String source;
  final IconData icon;

  const DemoActivity({
    required this.id,
    required this.title,
    required this.date,
    required this.amount,
    required this.source,
    required this.icon,
  });
}

const demoActivities = <DemoActivity>[
  DemoActivity(id: 'BTL-SAMPLE-1004', title: 'Electricity purchase', date: '28 Oct 2026',
    amount: '− M 200.00', source: 'Electricity', icon: Icons.bolt),
  DemoActivity(id: 'BTL-SAMPLE-1003', title: 'Wallet top-up', date: '26 Oct 2026',
    amount: '+ M 1,000.00', source: 'Demo wallet', icon: Icons.arrow_downward),
  DemoActivity(id: 'BTL-SAMPLE-1002', title: 'Loan repayment', date: '24 Oct 2026',
    amount: '− M 650.00', source: 'Personal loan', icon: Icons.account_balance),
  DemoActivity(id: 'BTL-SAMPLE-1001', title: 'Water payment', date: '22 Oct 2026',
    amount: '− M 150.00', source: 'WASCO', icon: Icons.water_drop),
];

class DemoActivityPage extends StatelessWidget {
  final DemoActivity activity;
  const DemoActivityPage({super.key, required this.activity});

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Transaction details')),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 680),
      child: ListView(padding: const EdgeInsets.all(20), children: [
        Card(color: Colors.white, child: Padding(
          padding: const EdgeInsets.all(22),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Icon(Icons.description_outlined, color: Color(0xFF113F3C), size: 42),
            const SizedBox(height: 12),
            const Text('SAMPLE TRANSACTION — NOT A RECEIPT',
              textAlign: TextAlign.center, style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF9A5405))),
            const SizedBox(height: 16),
            Text(activity.amount, textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 29, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text(activity.title, textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18)),
            const Divider(height: 36),
            _detail('Demo reference', activity.id),
            _detail('Date', activity.date),
            _detail('Service', activity.source),
            _detail('Status', 'Sample data only'),
            _detail('Currency', 'LSL'),
            const SizedBox(height: 20),
            const Text(
              'This screen illustrates how a future transaction receipt could look. '
              'It is not proof of payment. Verified receipts must come from '
              'IthutePay and the relevant payment provider.',
              style: TextStyle(color: Colors.black54, height: 1.5),
            ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Back to activity'),
            ),
          ]),
        )),
      ]),
    ))),
  );

  Widget _detail(String title, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 9),
    child: Row(children: [
      Expanded(child: Text(title, style: const TextStyle(color: Colors.black54))),
      const SizedBox(width: 12),
      Flexible(child: SelectableText(value, textAlign: TextAlign.right,
        style: const TextStyle(fontWeight: FontWeight.w600))),
    ]),
  );
}
