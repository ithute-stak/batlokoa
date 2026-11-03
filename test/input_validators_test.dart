import 'package:batlokoa/input_validators.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('amount allows positive LSL values with two decimals', () {
    expect(DemoInputValidator.amount('1'), isNull);
    expect(DemoInputValidator.amount('0.01'), isNull);
    expect(DemoInputValidator.amount('120.50'), isNull);
    expect(DemoInputValidator.amount('1000000'), isNull);
  });

  test('amount rejects invalid, unlimited, nonfinite and overprecision inputs', () {
    for (final invalid in <String>[
      '', '0', '-1', 'NaN', 'Infinity', '1e3', '5.999',
      '1000000.01', '1,000', 'one hundred',
    ]) {
      expect(DemoInputValidator.amount(invalid), isNotNull, reason: invalid);
    }
  });

  test('reference rejects empty or excessive input', () {
    expect(DemoInputValidator.reference(' '), isNotNull);
    expect(DemoInputValidator.reference('abc123'), isNull);
    expect(DemoInputValidator.reference('x' * 121), isNotNull);
  });
}
