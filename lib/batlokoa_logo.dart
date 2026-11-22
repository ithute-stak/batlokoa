import 'package:flutter/material.dart';

/// The official Batlokoa Financial Services artwork is bundled as an asset.
/// Keeping the original emblem in a separately loaded image avoids runtime
/// base64 decoding on mobile browsers and makes cache inspection easier.
class BatlokoaLogo extends StatelessWidget {
  final double size;
  const BatlokoaLogo({super.key, this.size = 64});

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Batlokoa Financial Services logo',
    image: true,
    child: Image.asset(
      'assets/branding/batlokoa_logo.webp',
      width: size,
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.high,
      errorBuilder: (context, error, stack) => SizedBox(
        width: size,
        height: size,
        child: const Center(
          child: Icon(Icons.broken_image_outlined, semanticLabel: 'Logo unavailable'),
        ),
      ),
    ),
  );
}
