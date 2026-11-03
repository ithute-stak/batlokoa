import 'package:flutter/material.dart';

import 'customer_session.dart';

/// Read-only session status. This page is safe to show in demo mode.
class CustomerSessionScreen extends StatefulWidget {
  final CustomerSessionRepository repository;

  const CustomerSessionScreen({
    super.key,
    this.repository = const DisabledSessionRepository(),
  });

  @override
  State<CustomerSessionScreen> createState() => _CustomerSessionScreenState();
}

class _CustomerSessionScreenState extends State<CustomerSessionScreen> {
  String message = 'Checking secure sign-in availability...';
  bool checking = true;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  Future<void> refresh() async {
    setState(() {
      checking = true;
      message = 'Checking secure sign-in availability...';
    });
    try {
      final authenticated = await widget.repository.isAuthenticated();
      if (!mounted) return;
      setState(() {
        checking = false;
        message = authenticated
            ? 'An authenticated gateway session is present. '
                'Loan account authorization is not confirmed.'
            : 'No authenticated gateway session is present.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        checking = false;
        message = 'Secure sign-in is not connected in this preview.';
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Secure sign-in status')),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.verified_user_outlined, size: 48),
                    const SizedBox(height: 16),
                    Text(message, textAlign: TextAlign.center),
                    if (checking) ...[
                      const SizedBox(height: 16),
                      const CircularProgressIndicator(),
                    ],
                    const SizedBox(height: 20),
                    OutlinedButton(
                      onPressed: checking ? null : refresh,
                      child: const Text('Check again'),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'This status does not enable loan access or payments.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
}
