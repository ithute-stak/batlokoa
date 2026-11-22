import 'package:flutter/material.dart';
import 'batlokoa_design.dart';

/// Consistent accessible BFS presentation primitives used across staff areas.
class BfsSectionTitle extends StatelessWidget {
  final String title;
  final String? eyebrow;
  final String? subtitle;
  const BfsSectionTitle({super.key, required this.title, this.eyebrow, this.subtitle});

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (eyebrow != null) ...[
        Text(eyebrow!.toUpperCase(), style: const TextStyle(
          letterSpacing: 1.4, color: BatlokoaDesign.primary,
          fontWeight: FontWeight.w800, fontSize: 10)),
        const SizedBox(height: 9),
      ],
      Text(title, style: const TextStyle(
        fontSize: 25, height: 1.2, color: BatlokoaDesign.navy,
        fontWeight: FontWeight.w800, letterSpacing: -0.7)),
      if (subtitle != null) ...[
        const SizedBox(height: 7),
        Text(subtitle!, style: const TextStyle(
          fontSize: 13, height: 1.5, color: BatlokoaDesign.silver)),
      ],
    ],
  );
}

class BfsActionPanel extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;
  final VoidCallback? onPressed;
  final bool disabled;
  final bool primary;
  const BfsActionPanel({
    super.key, required this.icon, required this.title,
    required this.description, this.onPressed,
    this.disabled = false, this.primary = false,
  });

  @override
  Widget build(BuildContext context) {
    const navy = BatlokoaDesign.navy;
    const red = BatlokoaDesign.primary;
    return Material(
      color: disabled ? const Color(0xFFF7F8FA)
          : primary ? navy : Colors.white,
      shape: RoundedRectangleBorder(
        side: BorderSide(color: disabled ? const Color(0xFFE7E9ED)
          : primary ? navy : const Color(0xFFE2E7EE)),
        borderRadius: BorderRadius.circular(20)),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: disabled ? null : onPressed,
        child: Padding(
          padding: const EdgeInsets.all(17),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Container(
                width: 46, height: 46, alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: primary ? const Color(0xFF34506E)
                    : disabled ? const Color(0xFFE9ECEF)
                    : const Color(0xFFFFE9EA),
                  borderRadius: BorderRadius.circular(14)),
                child: Icon(icon, size: 23, color: primary ? Colors.white
                  : disabled ? BatlokoaDesign.silver : red)),
              Icon(disabled ? Icons.lock_outline_rounded
                : Icons.arrow_outward_rounded, size: 20,
                color: primary ? Colors.white70 : BatlokoaDesign.silver),
            ]),
            const SizedBox(height: 18),
            Text(title, style: TextStyle(
              color: primary ? Colors.white : navy,
              fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 6),
            Text(description, maxLines: 3, overflow: TextOverflow.ellipsis,
              style: TextStyle(color: primary ? const Color(0xFFE0EAF5)
                : BatlokoaDesign.silver, fontSize: 12, height: 1.5)),
          ]),
        ),
      ),
    );
  }
}

class BfsPanel extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  const BfsPanel({super.key, required this.child,
    this.padding = const EdgeInsets.all(18)});

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(color: Colors.white,
      border: Border.all(color: const Color(0xFFE2E7EE)),
      borderRadius: BorderRadius.circular(20)),
    child: Padding(padding: padding, child: child),
  );
}

class BfsPill extends StatelessWidget {
  final String label;
  final Color color;
  final Color background;
  const BfsPill({super.key, required this.label,
    this.color = BatlokoaDesign.accent,
    this.background = const Color(0xFFEBF3FF)});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
    decoration: BoxDecoration(color: background,
      borderRadius: BorderRadius.circular(30)),
    child: Text(label, style: TextStyle(fontSize: 11,
      fontWeight: FontWeight.w700, color: color)),
  );
}
