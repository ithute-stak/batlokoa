import 'package:flutter/material.dart';

import 'batlokoa_design.dart';

/// Visual-only components. All values are fictional; never display these
/// for an authenticated customer or present them as live account balances.
class DemoBalanceCard extends StatelessWidget {
  final String label;
  final String amount;
  final String disclaimer;
  final Widget? actions;

  const DemoBalanceCard({
    super.key,
    required this.label,
    required this.amount,
    required this.disclaimer,
    this.actions,
  });

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(
          color: BatlokoaDesign.primary,
          borderRadius: BorderRadius.circular(BatlokoaDesign.cardRadius),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.info_outline, color: Colors.white, size: 16),
                SizedBox(width: 6),
                Text('DEMO ACCOUNT',
                    style: TextStyle(color: Colors.white,
                        fontSize: 12, fontWeight: FontWeight.bold)),
              ],
            ),
            const SizedBox(height: 14),
            Text(label, style: const TextStyle(color: Colors.white)),
            const SizedBox(height: 6),
            Text(amount,
                softWrap: true,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 32,
                    height: 1.18,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Text(disclaimer,
                style: const TextStyle(color: Colors.white, fontSize: 12)),
            if (actions != null) ...[
              const SizedBox(height: 18),
              actions!,
            ],
          ],
        ),
      );
}

/// Explicitly labels fictional instalments, rather than implying a live
/// repayment schedule or a due-date reminder.
class DemoRepaymentPreview extends StatelessWidget {
  const DemoRepaymentPreview({super.key});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Sample repayment schedule',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text('Illustrative instalments only — not amounts owed.',
              style: TextStyle(color: BatlokoaDesign.secondaryInk)),
          const SizedBox(height: 12),
          for (final entry in const [
            ('15 Nov 2026', 'M 650.00'),
            ('15 Dec 2026', 'M 650.00'),
            ('15 Jan 2027', 'M 650.00'),
          ]) ...[
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.calendar_month_outlined),
              title: Text(entry.$1),
              subtitle: const Text('Sample repayment'),
              trailing: Text(entry.$2,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
            ),
          ],
        ],
      );
}

/// A responsive wallet action surface, without calling payment services.
class DemoWalletActions extends StatelessWidget {
  final void Function(String action) onAction;
  const DemoWalletActions({super.key, required this.onAction});

  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, constraints) {
          final columns = constraints.maxWidth >= 550 ? 4 : 2;
          final textScale =
              MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0, 2.0);
          final tileHeight = 104.0 * textScale;
          const items = [
            ('Add money', Icons.add_circle_outline),
            ('Send money', Icons.send_outlined),
            ('Withdraw', Icons.account_balance_outlined),
            ('Repay loan', Icons.payments_outlined),
          ];
          return GridView.count(
            crossAxisCount: columns,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            mainAxisExtent: tileHeight,
            children: [
              for (final (label, icon) in items)
                OutlinedButton(
                  onPressed: () => onAction(label),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                        vertical: 12, horizontal: 6),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(icon),
                      const SizedBox(height: 6),
                      Text(label,
                          textAlign: TextAlign.center,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis),
                    ],
                  ),
                ),
            ],
          );
        },
      );
}
