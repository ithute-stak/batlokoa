import 'package:flutter/material.dart';

/// Protects a local-only, unsent demo form from accidental back navigation.
/// No draft is written to storage or submitted to any remote service.
class DemoDraftGuard extends StatelessWidget {
  final bool hasDraft;
  final Widget child;

  const DemoDraftGuard({
    super.key,
    required this.hasDraft,
    required this.child,
  });

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: !hasDraft,
        onPopInvokedWithResult: (didPop, result) async {
          if (didPop || !hasDraft) return;
          final discard = await showDialog<bool>(
            context: context,
            builder: (dialog) => AlertDialog(
              title: const Text('Discard demo draft?'),
              content: const Text(
                'Your unsent preview details will be lost. '
                'Nothing has been submitted or paid.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dialog, false),
                  child: const Text('Keep editing'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(dialog, true),
                  child: const Text('Discard draft'),
                ),
              ],
            ),
          );
          if (discard == true && context.mounted) {
            Navigator.of(context).pop();
          }
        },
        child: child,
      );
}
