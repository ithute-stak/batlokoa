import 'package:flutter/material.dart';

/// Accessible progress indicator for the three-step, local-only loan preview.
class DemoLoanProgress extends StatelessWidget {
  const DemoLoanProgress({super.key, required this.step});

  /// Zero-based position; this component is only used for the 3-step preview.
  final int step;

  @override
  Widget build(BuildContext context) {
    const steps = ['Choose your loan', 'Affordability details', 'Review your request'];
    final current = step.clamp(0, steps.length - 1);
    final label = 'Step ${current + 1} of ${steps.length}: ${steps[current]}';
    return Semantics(
      key: const Key('loan-step-progress'),
      container: true,
      liveRegion: true,
      label: label,
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Step ${current + 1} of ${steps.length}'),
            const SizedBox(height: 8),
            LinearProgressIndicator(value: (current + 1) / steps.length),
          ],
        ),
      ),
    );
  }
}
