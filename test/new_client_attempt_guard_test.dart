import 'package:flutter_test/flutter_test.dart';
import 'package:batlokoa/new_client_attempt_guard.dart';

void main() {
  test('same payload retries preserve the original idempotency key', () {
    final attempt = NewClientAttemptGuard('synthetic-stable-key-0001');
    final original = <String, dynamic>{
      'branch_id': 'synthetic-branch',
      'first_name': 'Synthetic',
      'external_debts': [
        {'creditor': 'Lender', 'current_balance': '500.00'}
      ],
    };
    attempt.prepare(original);
    expect(attempt.attempted, true);
    expect(attempt.confirmed, false);
    attempt.prepare(original);
    expect(attempt.idempotencyKey, 'synthetic-stable-key-0001');
  });

  test('changed values after an uncertain save are rejected', () {
    final attempt = NewClientAttemptGuard('synthetic-stable-key-0002');
    attempt.prepare({'first_name': 'Synthetic', 'branch_id': 'branch-a'});
    expect(() => attempt.prepare({
      'first_name': 'Other', 'branch_id': 'branch-a',
    }), throwsStateError);
    expect(() => attempt.prepare({
      'first_name': 'Synthetic', 'branch_id': 'branch-b',
    }), throwsStateError);
  });

  test('confirmed registration cannot be submitted again', () {
    final attempt = NewClientAttemptGuard('synthetic-stable-key-0003');
    expect(() => attempt.confirm(), throwsStateError);
    attempt.prepare({'national_id': 'SYNTHETIC-ONLY'});
    attempt.confirm();
    expect(attempt.confirmed, true);
    expect(() => attempt.prepare({'national_id': 'SYNTHETIC-ONLY'}),
        throwsStateError);
    expect(() => attempt.confirm(), throwsStateError);
  });

  test('failed request before any attempt does not lock the form', () {
    final attempt = NewClientAttemptGuard('synthetic-stable-key-0004');
    expect(attempt.attempted, false);
    attempt.prepare({'first_name': 'Synthetic'});
    expect(attempt.attempted, true);
  });
}
