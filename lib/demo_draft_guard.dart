import 'package:flutter/material.dart';

/// Guards local-only, unsent demo forms from accidental back navigation.
/// No draft is saved to persistent storage or submitted to a remote service.
class DemoDraftGuard extends StatefulWidget {
  final bool hasDraft;
  final Widget child;

  const DemoDraftGuard({
    super.key,
    required this.hasDraft,
    required this.child,
  });

  @override
  State<DemoDraftGuard> createState() => _DemoDraftGuardState();
}

class _DemoDraftGuardState extends State<DemoDraftGuard> {
  bool _confirmedDiscard = false;
  bool _confirming = false;

  Future<void> _confirmExit() async {
    if (_confirming) return;
    _confirming = true;
    try {
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
      if (discard != true || !mounted) return;
      setState(() => _confirmedDiscard = true);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) Navigator.of(context).pop();
      });
    } finally {
      _confirming = false;
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: !widget.hasDraft || _confirmedDiscard,
        onPopInvokedWithResult: (didPop, result) {
          if (!didPop && widget.hasDraft && !_confirmedDiscard) {
            _confirmExit();
          }
        },
        child: widget.child,
      );
}
