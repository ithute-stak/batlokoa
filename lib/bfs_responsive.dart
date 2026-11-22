import 'package:flutter/material.dart';

/// Shared breakpoints for Batlokoa's phone-first staff application.
/// Never clamp the user's system text scale: allow content to reflow/scroll.
abstract final class BfsResponsive {
  static double width(BuildContext context) => MediaQuery.sizeOf(context).width;
  static double textScale(BuildContext context) =>
      MediaQuery.textScalerOf(context).scale(1);

  static EdgeInsets pagePadding(BuildContext context) {
    final width = BfsResponsive.width(context);
    final horizontal = width < 350 ? 12.0 : width < 600 ? 16.0 : 24.0;
    return EdgeInsets.fromLTRB(horizontal, 20, horizontal, 36);
  }

  static bool isCompact(BuildContext context) =>
      width(context) < 390 || textScale(context) > 1.35;

  static double navigationHeight(BuildContext context) {
    if (MediaQuery.sizeOf(context).height < 450) return 64;
    final scale = textScale(context);
    return scale >= 2 ? 104 : scale > 1.35 ? 88 : 76;
  }
}
