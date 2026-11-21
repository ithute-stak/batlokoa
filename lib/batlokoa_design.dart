import 'package:flutter/material.dart';

/// Batlokoa Financial Services colours from the existing BFS web brand system.
///
/// The logo artwork itself is a separate binary asset; do not reproduce it
/// with a generated image or substitute another company's logo.
abstract final class BatlokoaDesign {
  static const Color primary = Color(0xFFD71920); // BFS red
  static const Color primaryDark = Color(0xFFA80F18);
  static const Color accent = Color(0xFF075EB6); // BFS blue
  static const Color navy = Color(0xFF12233F);
  static const Color silver = Color(0xFF667085);
  static const Color canvas = Color(0xFFF5F7FB);
  static const Color surface = Colors.white;
  static const Color border = Color(0xFFE5E7EB);
  static const Color ink = Color(0xFF172033);
  static const Color secondaryInk = silver;

  static const String companyName = 'Batlokoa Financial Services';
  static const String motto = 'We make Your Debt Affordable.';

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
      secondary: accent,
      surface: surface,
    );
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: canvas,
      colorScheme: scheme,
      appBarTheme: const AppBarTheme(
        backgroundColor: surface,
        foregroundColor: navy,
      ),
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 27, height: 1.2, fontWeight: FontWeight.w800, color: navy,
        ),
        titleLarge: TextStyle(
          fontSize: 21, height: 1.25, fontWeight: FontWeight.w700, color: navy,
        ),
        titleMedium: TextStyle(
          fontSize: 17, height: 1.3, fontWeight: FontWeight.w700, color: navy,
        ),
        bodyMedium: TextStyle(
          fontSize: 14, height: 1.45, color: ink,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16, vertical: 15,
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
        indicatorColor: Color(0xFFFFE5E7),
      ),
      navigationRailTheme: const NavigationRailThemeData(
        backgroundColor: surface,
        indicatorColor: Color(0xFFFFE5E7),
      ),
    );
  }
}
