import 'package:flutter/material.dart';

/// An explicitly non-transactional review page. The final button never sends a request.
class DemoPaymentReview extends StatefulWidget {
  final String title;
  final String amount;
  final String reference;
  final String method;

  const DemoPaymentReview({
    super.key,
    required this.title,
    required this.amount,
    required this.reference,
    required this.method,
  });

  @override
  State<DemoPaymentReview> createState() => _DemoPaymentReviewState();
}

class _DemoPaymentReviewState extends State<DemoPaymentReview> {
  bool _confirmationOpen = false;
  bool _previewViewed = false;

  Future<void> _previewConfirmation() async {
    if (_confirmationOpen) return;
    setState(() => _confirmationOpen = true);
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Demo complete'),
          content: const Text(
            'This is a visual preview. No transaction was made and no receipt was issued.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    } finally {
      if (mounted) setState(() { _confirmationOpen = false; _previewViewed = true; });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Review payment')),
    body: SafeArea(
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 600),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Card(
                color: Colors.white,
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.receipt_long_outlined, size: 44, color: Color(0xFF113F3C)),
                      const SizedBox(height: 12),
                      const Text(
                        'Transaction preview',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 23, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 8),
                      Semantics(
                        container: true,
                        liveRegion: true,
                        label: 'Demo preview only. No money will be sent.',
                        child: ExcludeSemantics(
                          child: Text(
                            'No money will be sent. This summary uses the details you entered.',
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                      const Divider(height: 36),
                      _line('Service', widget.title),
                      _line('Amount', 'M ' + widget.amount),
                      _line('Reference', widget.reference.isEmpty ? '—' : widget.reference),
                      _line('Payment method', widget.method),
                      _line('Provider fees', 'Not available in demo'),
                      const SizedBox(height: 18),
                      const Text(
                        'A live flow must verify recipient details, fees, limits and payment status with IthutePay before authorisation.',
                        style: TextStyle(fontSize: 13, color: Colors.black54),
                      ),
                      const SizedBox(height: 20),
                      FilledButton.icon(
                        onPressed: _confirmationOpen ? null : _previewConfirmation,
                        icon: const Icon(Icons.visibility_outlined),
                        label: const Text('Preview confirmation'),
                      ),
                      const SizedBox(height: 8),
                      if (_previewViewed) Semantics(
                        container: true,
                        liveRegion: true,
                        label: 'Preview closed. No payment was made. Your details are unchanged.',
                        child: const ExcludeSemantics(
                          child: Text(
                            'Preview closed — no payment was made. Your details are unchanged.',
                            key: Key('demo-preview-closed-status'),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      ),
                      OutlinedButton(
                        onPressed: () => Navigator.pop(context, true),
                        child: const Text('Edit details'),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Editing returns to your unsent form. Confirming this preview never authorises a payment.',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 12, color: Colors.black54),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  Widget _line(String title, String value) => Builder(
    builder: (context) => LayoutBuilder(
      builder: (context, constraints) {
        final stacked = constraints.maxWidth < 300 ||
            MediaQuery.textScalerOf(context).scale(1.0) > 1.35;
        final label = Text(title, style: const TextStyle(color: Colors.black54));
        final amount = Text(value,
          textAlign: stacked ? TextAlign.start : TextAlign.end,
          style: const TextStyle(fontWeight: FontWeight.w700));
        return Semantics(
          container: true,
          label: '$title: $value',
          child: ExcludeSemantics(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 9),
              child: stacked
                  ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      label,
                      const SizedBox(height: 4),
                      amount,
                    ])
                  : Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Expanded(child: label),
                      const SizedBox(width: 12),
                      Flexible(child: amount),
                    ]),
            ),
          ),
        );
      },
    ),
  );
}
