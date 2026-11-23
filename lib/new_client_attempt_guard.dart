import 'dart:convert';

/// In-memory guard for one new-client registration attempt.
///
/// A network timeout is not proof that LoanHub rolled the transaction back.
/// Reuse the original key and exactly the original payload; refuse edits and
/// additional writes after the server has confirmed an account.
class NewClientAttemptGuard {
  NewClientAttemptGuard(this.idempotencyKey);

  final String idempotencyKey;
  String? _firstPayload;
  bool _confirmed = false;

  bool get confirmed => _confirmed;
  bool get attempted => _firstPayload != null;

  void prepare(Map<String, dynamic> payload) {
    if (_confirmed) {
      throw StateError('Registration already confirmed');
    }
    final encoded = jsonEncode(payload);
    if (_firstPayload != null && _firstPayload != encoded) {
      throw StateError(
          'Registration details changed after an uncertain save');
    }
    _firstPayload ??= encoded;
  }

  void confirm() {
    if (!attempted || _confirmed) {
      throw StateError('Cannot confirm an unsubmitted registration');
    }
    _confirmed = true;
  }
}
