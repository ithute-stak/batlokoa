import 'package:flutter/material.dart';

/// Visible, screen-reader accessible error summary for unsent demo forms.
class DemoFormError extends StatelessWidget {
  final String message;
  final VoidCallback? onRetry;

  const DemoFormError({super.key, required this.message, this.onRetry});

  @override
  Widget build(BuildContext context) => Semantics(
        liveRegion: true,
        label: 'Form error: $message',
        child: Container(
          key: const Key('demo-form-error'),
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: const Color(0xFFFFF4F2),
            border: Border.all(color: const Color(0xFFB3261E)),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.error_outline,
                  color: Color(0xFFB3261E), size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(message,
                        style: const TextStyle(
                            color: Color(0xFF7D1D17),
                            fontWeight: FontWeight.w600)),
                    if (onRetry != null)
                      TextButton(
                        onPressed: onRetry,
                        child: const Text('Correct details'),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
}
