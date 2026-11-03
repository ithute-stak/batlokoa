import 'package:flutter/material.dart';

/// Provisional design system for the six-screen Flutter preview.
///
/// These are NOT official Batlokoa Financial Services brand colours.
/// Replace only after official brand assets and colour codes are approved.
abstract final class BatlokoaDesign {
  static const Color primary = Color(0xFF113F3C);
  static const Color accent = Color(0xFF16A48B);
  static const Color canvas = Color(0xFFF4F8F7);
  static const Color surface = Colors.white;
  static const Color border = Color(0xFFE4ECEA);
  static const Color ink = Color(0xFF1B2927);
  static const Color secondaryInk = Color(0xFF52615E);

  static const double cardRadius = 20;
  static const double buttonRadius = 14;
  static const double fieldRadius = 14;
  static const double minTapHeight = 48;

  static EdgeInsets pagePadding(double width) => EdgeInsets.symmetric(
        horizontal: width < 360 ? 12 : width < 760 ? 18 : 28,
        vertical: width < 760 ? 18 : 28,
      );

  static ThemeData theme() {
    final scheme = ColorScheme.fromSeed(
      seedColor: primary,
      primary: primary,
      surface: surface,
    );
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: canvas,
      colorScheme: scheme,
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 27,
          height: 1.2,
          fontWeight: FontWeight.w800,
          color: ink,
        ),
        titleLarge: TextStyle(
          fontSize: 21,
          height: 1.25,
          fontWeight: FontWeight.w700,
          color: ink,
        ),
        titleMedium: TextStyle(
          fontSize: 17,
          height: 1.3,
          fontWeight: FontWeight.w700,
          color: ink,
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          height: 1.45,
          color: ink,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 15,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(fieldRadius),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, minTapHeight),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(buttonRadius),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, minTapHeight),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(buttonRadius),
          ),
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        height: 76,
        backgroundColor: surface,
        indicatorColor: Color(0xFFDDEFEA),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: surface,
        indicatorColor: Color(0xFFDDEFEA),
      ),
    );
  }
}
