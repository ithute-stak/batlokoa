import 'package:flutter/material.dart';

/// Reusable presentation states for future authenticated API repositories.
sealed class Loadable<T> {
  const Loadable();
}

final class Loading<T> extends Loadable<T> {
  const Loading();
}

final class Loaded<T> extends Loadable<T> {
  final T value;
  const Loaded(this.value);
}

final class Empty<T> extends Loadable<T> {
  const Empty();
}

final class Failed<T> extends Loadable<T> {
  final String message;
  const Failed(this.message);
}

/// Never displays fabricated financial data while a request is in progress.
class LoadableView<T> extends StatelessWidget {
  final Loadable<T> state;
  final Widget Function(BuildContext context, T data) builder;
  final VoidCallback? onRetry;
  final String emptyTitle;

  const LoadableView({
    super.key,
    required this.state,
    required this.builder,
    this.onRetry,
    this.emptyTitle = 'Nothing to show yet',
  });

  @override
  Widget build(BuildContext context) {
    return switch (state) {
      Loading<T>() => const Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              CircularProgressIndicator(),
              SizedBox(height: 14),
              Text('Loading your information…'),
            ]),
          ),
        ),
      Loaded<T>(value: final data) => builder(context, data),
      Empty<T>() => _MessageState(
          icon: Icons.inbox_outlined,
          title: emptyTitle,
          description: 'Your information will appear here when available.',
        ),
      Failed<T>(message: final message) => _MessageState(
          icon: Icons.wifi_off_outlined,
          title: 'Unable to load',
          description: message,
          onRetry: onRetry,
        ),
    };
  }
}

class _MessageState extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final VoidCallback? onRetry;

  const _MessageState({
    required this.icon,
    required this.title,
    required this.description,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(icon, size: 42, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 12),
              Text(title, textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(description, textAlign: TextAlign.center),
              if (onRetry != null) ...[
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Try again'),
                ),
              ],
            ]),
          ),
        ),
      );
}
