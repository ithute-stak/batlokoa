import 'package:flutter/material.dart';
import 'staff_gateway.dart';
import 'staff_client_registration_payload.dart';
import 'new_client_attempt_guard.dart';
import 'batlokoa_design.dart';
import 'bfs_responsive.dart';
import 'bfs_widgets.dart';
import 'staff_client_directory_screen.dart';

/// Local-only assisted registration preparation. There are deliberately no
/// POST calls, persistence, drafts in storage, or registration confirmations.
class StaffClientRegistrationScreen extends StatefulWidget {
  final StaffSession staff;
  final StaffGateway gateway;
  const StaffClientRegistrationScreen({
    super.key, required this.staff, this.gateway = const DisabledStaffGateway(),
  });

  @override
  State<StaffClientRegistrationScreen> createState() =>
      _StaffClientRegistrationScreenState();
}

class _StaffClientRegistrationScreenState
    extends State<StaffClientRegistrationScreen> {
  final _form = GlobalKey<FormState>();
  // One active stage is built at a time; values remain in memory until exit.
  int _step = -1;
  bool _identityChecked = false;
  bool _checkingIdentity = false;
  bool _possibleExistingIdentity = false;
  String? _identityMessage;
  String? _checkedNationalId;
  String? _checkedBranch;
  static const _steps = [
    'Personal details', 'Identity and address', 'Employment and loans',
    'Banking details', 'Consent and review',
  ];
  final _extra = <String, TextEditingController>{};
  final _choice = <String, String>{
    'marital_status': '', 'employment_type': '',
    'gender': 'male', 'employment_status': 'employed',
    'bank_name': '', 'bank_account_type': 'savings',
  };
  bool _hasExistingLoans = false;
  bool _salaryAccount = false;
  final _externalDebt = <Map<String, TextEditingController>>[];
  void _addDebt() => setState(() => _externalDebt.add({
    'creditor': TextEditingController(),
    'current_balance': TextEditingController(),
    'installment_amount': TextEditingController(),
    'remaining_installments': TextEditingController(),
  }));
  Widget _debtItem(int index) {
    final debt = _externalDebt[index];
    Widget input(String key, String label) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: TextFormField(
        key: Key('register-debt-' + index.toString() + '-' + key),
        controller: debt[key],
        decoration: InputDecoration(labelText: label),
        keyboardType: key == 'creditor' ? TextInputType.text
            : const TextInputType.numberWithOptions(decimal: true),
        validator: (v) {
          final value = (v ?? '').trim();
          if (value.isEmpty) return 'Required';
          if (key == 'creditor') return value.length < 2 ? 'Enter lender name' : null;
          return double.tryParse(value) == null || double.parse(value) < 0
              ? 'Enter a valid non-negative number' : null;
        },
      ),
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 15),
      child: BfsPanel(child: Column(children: [
        Row(children: [
          Expanded(child: Text('Existing debt ' + (index + 1).toString(),
              style: const TextStyle(fontWeight: FontWeight.w800))),
          IconButton(icon: const Icon(Icons.delete_outline),
            tooltip: 'Remove debt',
            onPressed: () => setState(() {
              final removed = _externalDebt.removeAt(index);
              WidgetsBinding.instance.addPostFrameCallback((_) {
                for (final c in removed.values) { c.dispose(); }
              });
            })),
        ]),
        input('creditor', 'Lender / creditor'),
        input('current_balance', 'Outstanding balance'),
        input('installment_amount', 'Monthly instalment'),
        input('remaining_installments', 'Instalments remaining'),
      ])),
    );
  }
  void _nextStep() {
    if (_step == -1) {
      if (!_identityChecked ||
          _checkedNationalId != _nationalId.text.trim() ||
          _checkedBranch != _branch) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Check the National ID with LoanHub before continuing.')));
        return;
      }
      setState(() => _step = 0);
      return;
    }
    if (!_identityChecked ||
        _checkedNationalId != _nationalId.text.trim() ||
        _checkedBranch != _branch) {
      setState(() => _step = -1);
      return;
    }
    if (_form.currentState?.validate() != true) return;
    if (_step == 0 && _branch == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select an authorized branch.')));
      return;
    }
    if (_step == 1 &&
        _nationalId.text.trim().isEmpty &&
        _passport.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('National ID or passport is required.')));
      return;
    }
    if (_step == 2 && _hasExistingLoans) {
      final total = double.tryParse(_x('existing_loan_total').text) ?? 0;
      if (total <= 0) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Existing loans require an outstanding balance.')));
        return;
      }
    }
    if (_step < 4) {
      final openingReview = _step == 3;
      setState(() {
        _step++;
        _review = false;
        _serverResult = null;
      });
      if (openingReview) _fetchReadiness();
    }
  }

  Future<void> _fetchReadiness() async {
    if (_readinessLoading || _readinessChecked) return;
    if (widget.gateway is! StaffRegistrationReadinessGateway) {
      setState(() {
        _readinessChecked = true;
        _readinessMessage = 'LoanHub release status is unavailable. '
            'Client creation remains disabled.';
      });
      return;
    }
    setState(() => _readinessLoading = true);
    try {
      final result = await (widget.gateway as StaffRegistrationReadinessGateway)
          .registrationReadiness();
      if (!mounted) return;
      setState(() {
        _readinessChecked = true;
        _readinessMessage = result.canCreateClient
            ? 'Registration release requires a separate security review.'
            : 'LoanHub confirms that new-client registration is not released. '
              'Identity migration approval and an independent release '
              'are required before submission can be enabled.';
      });
    } catch (_) {
      if (mounted) setState(() {
        _readinessChecked = true;
        _readinessMessage = 'LoanHub registration release status could not '
            'be verified. Client submission remains disabled.';
      });
    } finally {
      if (mounted) setState(() => _readinessLoading = false);
    }
  }

  Future<void> _checkNationalId() async {
    if (_checkingIdentity || _loadingBranches) return;
    final nationalId = _nationalId.text.trim();
    final branchId = _branch;
    if (nationalId.length < 4 || nationalId.length > 100 || branchId == null) {
      setState(() {
        _identityChecked = false;
        _possibleExistingIdentity = false;
        _identityMessage = 'Enter a valid National ID and select the branch.';
      });
      return;
    }
    if (widget.gateway is! StaffNationalIdGateway) {
      setState(() {
        _identityChecked = false;
        _possibleExistingIdentity = false;
        _identityMessage = 'Identity screening is not available. Registration cannot continue.';
      });
      return;
    }
    setState(() {
      _checkingIdentity = true;
      _identityChecked = false;
      _possibleExistingIdentity = false;
      _identityMessage = null;
    });
    try {
      final result = await (widget.gateway as StaffNationalIdGateway)
          .checkNationalId(nationalId: nationalId, branchId: branchId);
      if (!mounted) return;
      if (_nationalId.text.trim() != nationalId || _branch != branchId) {
        setState(() { _identityMessage = 'The ID or branch changed. Check again.'; });
        return;
      }
      setState(() {
        _identityChecked = result.mayContinuePreparation;
        _possibleExistingIdentity = result.status == 'existing_or_review';
        _checkedNationalId = result.mayContinuePreparation ? nationalId : null;
        _checkedBranch = result.mayContinuePreparation ? branchId : null;
        _identityMessage = result.mayContinuePreparation
            ? 'No matching identity was returned in this review. You may prepare '
              'the details, but final duplicate checks and client approval are still required.'
            : 'A possible existing identity or legacy record needs manual review. '
              'Do not create a duplicate client. Use Find clients or ask an authorized '
              'LoanHub administrator to investigate.';
      });
    } catch (_) {
      if (mounted) setState(() {
        _identityChecked = false;
        _possibleExistingIdentity = false;
        _identityMessage = 'Identity screening could not be completed. '
            'No registration may proceed until the check succeeds.';
      });
    } finally {
      if (mounted) setState(() => _checkingIdentity = false);
    }
  }

  void _identityEdited() {
    if (_identityChecked || _identityMessage != null) {
      setState(() {
        _identityChecked = false;
        _possibleExistingIdentity = false;
        _checkedNationalId = null;
        _checkedBranch = null;
        _identityMessage = null;
      });
    }
  }

  bool _loadingBranches = false;
  List<Map<String, String>> _availableBranches = const [];
  TextEditingController _x(String key) =>
      _extra.putIfAbsent(key, TextEditingController.new);
  Widget _extraField(String key, String label, {TextInputType? type, bool sensitive = false}) =>
    Padding(padding: const EdgeInsets.only(bottom: 14), child: TextFormField(
      key: Key('register-' + key.replaceAll('_', '-')),
      controller: _x(key),
      maxLength: key == 'physical_address' ? 500 : 150,
      keyboardType: type,
      autocorrect: !sensitive, enableSuggestions: !sensitive,
      decoration: InputDecoration(labelText: label),
      validator: (value) {
        final text = (value ?? '').trim();
        if (key == 'income_day' && text.isNotEmpty) {
          final day = int.tryParse(text);
          if (day == null || day < 1 || day > 31) return 'Use a day between 1 and 31';
        }
        if (const {'existing_loan_total'}.contains(key) &&
            text.isNotEmpty &&
            !RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(text)) {
          return 'Enter an amount with up to two decimals';
        }
        if ((_choice['bank_name'] ?? '').isNotEmpty &&
            key == 'bank_account_holder' && text.length < 2) {
          return 'Enter the account holder';
        }
        if ((_choice['bank_name'] ?? '').isNotEmpty &&
            key == 'bank_account_number' &&
            (text.length < 4 || text.length > 40)) {
          return 'Enter a valid account number';
        }
        return null;
      },
    ));
  Widget _select(String key, String label, Map<String, String> options) =>
    Padding(padding: const EdgeInsets.only(bottom: 14),
      child: DropdownButtonFormField<String>(
        key: Key('register-' + key.replaceAll('_', '-')),
        value: _choice[key]!.isEmpty ? null : _choice[key],
        isExpanded: true,
        decoration: InputDecoration(labelText: label),
        items: [for (final option in options.entries) DropdownMenuItem(
          value: option.key,
          child: Text(option.value, overflow: TextOverflow.ellipsis))],
        onChanged: (v) => setState(() {
          _choice[key] = v ?? '';
          if (key == 'gender') _gender.text = v ?? '';
          if (key == 'employment_status') _employment.text = v ?? '';
        }),
      ));

  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _phone = TextEditingController();
  final _birthDate = TextEditingController();
  final _nationalId = TextEditingController();
  final _passport = TextEditingController();
  final _district = TextEditingController();
  final _income = TextEditingController();
  final _gender = TextEditingController();
  final _employment = TextEditingController();
  String? _branch;
  bool _shareConsent = false;
  bool _creditConsent = false;
  bool _review = false;
  bool _serverBusy = false;
  bool _readinessLoading = false;
  bool _readinessChecked = false;
  String? _readinessMessage;
  String? _serverResult;

  @override
  void initState() {
    super.initState();
    if (!widget.staff.companyWide && widget.staff.branchIds.length == 1) {
      _branch = widget.staff.branchIds.single;
    }
    _gender.text = 'male';
    _employment.text = 'employed';
    _x('nationality').text = 'Mosotho';
    _loadBranches();
  }

  Future<void> _loadBranches() async {
    if (widget.staff.companyWide &&
        widget.gateway is OwnerStaffManagementGateway) {
      setState(() => _loadingBranches = true);
      try {
        final items = await (widget.gateway as OwnerStaffManagementGateway)
            .ownerBranches();
        if (!mounted) return;
        setState(() {
          _availableBranches = items
              .where((v) => v['id'] is String && v['name'] is String)
              .map((v) => {'id': v['id'] as String, 'name': v['name'] as String})
              .toList();
          _loadingBranches = false;
        });
      } catch (_) {
        if (mounted) setState(() => _loadingBranches = false);
      }
    } else {
      _availableBranches = [
        for (final id in widget.staff.branchIds) {'id': id, 'name': id},
      ];
    }
  }

  String? _required(String? value) =>
      value == null || value.trim().isEmpty || value.trim().length > 100
          ? 'Required (maximum 100 characters)' : null;

  String? _validatePhone(String? value) =>
      value == null || value.trim().length < 8 || value.trim().length > 30
          ? 'Enter a valid phone number' : null;

  String? _validateDob(String? value) {
    if (value == null || !RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(value)) {
      return 'Use YYYY-MM-DD';
    }
    final parsed = DateTime.tryParse(value);
    if (parsed == null || parsed.year < 1900 ||
        !parsed.isBefore(DateTime.now()) ||
        parsed.toIso8601String().substring(0, 10) != value) {
      return 'Enter a valid past date';
    }
    return null;
  }

  String? _validateIncome(String? value) {
    if (value == null || value.trim().isEmpty) return null;
    if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(value.trim())) {
      return 'Enter a non-negative amount with up to 2 decimals';
    }
    return null;
  }

  void _prepareReview() {
    if (!_identityChecked ||
        _checkedNationalId != _nationalId.text.trim() ||
        _checkedBranch != _branch) {
      setState(() { _review = false; _step = -1; });
      return;
    }
    if (!_form.currentState!.validate()) {
      setState(() => _review = false);
      return;
    }
    if (_branch == null || _branch!.isEmpty || (_nationalId.text.trim().isEmpty &&
        _passport.text.trim().isEmpty)) {
      setState(() => _review = false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Select an assigned branch and provide national ID or passport.'),
      ));
      return;
    }
    setState(() { _review = true; _serverResult = null; });
  }


  Future<void> _validateOnServer() async {
    if (_serverBusy || !_review || _branch == null ||
        !_identityChecked ||
        _checkedNationalId != _nationalId.text.trim() ||
        _checkedBranch != _branch) return;
    // The browser sends input only on an explicit employee action.
    // Never persist this sensitive draft or claim identity clearance.
    setState(() {
      _serverBusy = true;
      _serverResult = null;
    });
    try {
      final result = await widget.gateway.validateRegistration({
        'first_name': _firstName.text.trim(),
        'last_name': _lastName.text.trim(),
        'phone': _phone.text.trim(),
        'date_of_birth': _birthDate.text.trim(),
        'gender': _gender.text.trim(),
        'district': _district.text.trim(),
        'employment_status': _employment.text.trim(),
        'branch_id': _branch,
        'national_id': _nationalId.text.trim().isEmpty
            ? null : _nationalId.text.trim(),
        'passport_number': _passport.text.trim().isEmpty
            ? null : _passport.text.trim(),
        'monthly_income': _income.text.trim().isEmpty
            ? null : _income.text.trim(),
        'consent_to_share_profile': _shareConsent,
        'consent_to_credit_checks': _creditConsent,
      });
      if (!mounted) return;
      if (result.branchId != _branch ||
          !result.identityReviewRequired) {
        throw const FormatException('Untrusted review scope');
      }
      setState(() => _serverResult =
          'Server validation completed. Identity and legacy record review '
          'are still required. Submission remains unavailable.');
    } catch (_) {
      if (mounted) setState(() => _serverResult =
          'Server validation unavailable. No client was registered.');
    } finally {
      if (mounted) setState(() => _serverBusy = false);
    }
  }

  /// Maps all supported fields, including debts and bank details, without
  /// saving a browser draft or mistaking identity preflight for authorization.
  Map<String, dynamic> _completeRegistrationPayload() =>
      buildNewClientRegistrationPayload(
        branchId: _branch!,
        firstName: _firstName.text,
        lastName: _lastName.text,
        phone: _phone.text,
        dateOfBirth: _birthDate.text,
        gender: _gender.text,
        district: _district.text,
        employmentStatus: _employment.text,
        nationalId: _nationalId.text,
        passportNumber: _passport.text,
        extra: {for (final entry in _extra.entries) entry.key: entry.value.text},
        choices: _choice,
        monthlyIncome: _income.text,
        hasExistingLoans: _hasExistingLoans,
        salaryAccount: _salaryAccount,
        externalDebts: [
          for (final debt in _externalDebt)
            {for (final entry in debt.entries) entry.key: entry.value.text},
        ],
        profileConsent: _shareConsent,
        creditConsent: _creditConsent,
      );

  // The current LoanHub release is not approved. Keep this false until an
  // independently reviewed release supplies real server-side authorization.
  bool get _clientWritesReleased => false;
  // Reuse a request key on retries; never make ambiguous network failures
  // create a second borrower account.
  final String _registrationRequestKey = 'batlokoa-' +
      DateTime.now().microsecondsSinceEpoch.toString() + '-register';
  bool _savingClient = false;
  late final NewClientAttemptGuard _attempt = NewClientAttemptGuard(
      _registrationRequestKey);
  String? _clientSaveResult;

  Future<void> _saveNewClient() async {
    if (!_clientWritesReleased || !_review || !_identityChecked ||
        _checkedNationalId != _nationalId.text.trim() ||
        _checkedBranch != _branch || _branch == null || _savingClient ||
        _attempt.confirmed ||
        widget.gateway is! StaffNewClientCreationGateway) return;
    if (_form.currentState?.validate() != true) return;
    setState(() { _savingClient = true; _clientSaveResult = null; });
    try {
      final payload = _completeRegistrationPayload();
      try {
        _attempt.prepare(payload);
      } on StateError {
        if (mounted) setState(() => _clientSaveResult =
            'Registration details changed or already confirmed. '
            'Check LoanHub before starting a new registration.');
        return;
      }
      final receipt = await (widget.gateway as StaffNewClientCreationGateway)
          .createNewClient(payload,
            idempotencyKey: _registrationRequestKey);
      if (!mounted) return;
      setState(() {
        _attempt.confirm();
        _clientSaveResult = receipt.replayed
            ? 'Previous registration confirmed in LoanHub.'
            : 'Client registered in LoanHub. Account: ' + receipt.clientAccountId;
      });
    } catch (_) {
      if (mounted) setState(() => _clientSaveResult =
          'LoanHub did not confirm registration. No success is claimed.');
    } finally {
      if (mounted) setState(() => _savingClient = false);
    }
  }

  @override
  void dispose() {
    for (final controller in [
      _firstName, _lastName, _phone, _birthDate, _nationalId,
      _passport, _district, _income, _gender, _employment,
    ]) {
      controller.dispose();
    }
    for (final controller in _extra.values) { controller.dispose(); }
    for (final debt in _externalDebt) {
      for (final controller in debt.values) { controller.dispose(); }
    }
    super.dispose();
  }

  Widget _field(String name, TextEditingController controller, {
    String? Function(String?)? validate,
    TextInputType? type,
    String? hint,
    bool sensitive = false,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 14),
    child: TextFormField(
      key: Key('register-${name.toLowerCase().replaceAll(' ', '-')}'),
      controller: controller,
      keyboardType: type,
      maxLength: sensitive ? 100 : 100,
      autocorrect: !sensitive,
      enableSuggestions: !sensitive,
      textCapitalization: sensitive ? TextCapitalization.none
          : TextCapitalization.sentences,
      // National ID must remain visible for a clerical accuracy check;
      // suggestions and autocorrect are still disabled for sensitive data.
      obscureText: sensitive && controller != _nationalId,
      decoration: InputDecoration(
        labelText: name, hintText: hint,
        border: const OutlineInputBorder(),
      ),
      validator: validate,
      onChanged: (_) {
        if (controller == _nationalId) _identityEdited();
        if (_review) setState(() {
        _review = false; _serverResult = null;
      }); },
    ),
  );


  Widget _identityFirst() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const BfsPanel(child: Row(children: [
        Icon(Icons.badge_outlined, color: BatlokoaDesign.primary),
        SizedBox(width: 13),
        Expanded(child: Text('Start by checking the client National ID '
            'against existing and historical LoanHub records. '
            'Do not collect other details until this check succeeds.',
            style: TextStyle(height: 1.5))),
      ])),
      const SizedBox(height: 22),
      _field('National ID', _nationalId, sensitive: true,
          validate: (value) {
            final id = (value ?? '').trim();
            return id.length < 4 || id.length > 100
                ? 'Enter a valid National ID (4–100 characters)' : null;
          }),
      if (_loadingBranches) const LinearProgressIndicator(),
      if (!_loadingBranches && _availableBranches.isEmpty)
        const BfsPanel(child: Text('An authorized registration branch is '
            'required before checking the ID. Contact your administrator '
            'if no branch is available.')),
      if (_availableBranches.isNotEmpty)
        Padding(padding: const EdgeInsets.only(bottom: 15),
          child: DropdownButtonFormField<String>(
            key: const Key('register-branch'),
            value: _branch != null &&
                _availableBranches.any((b) => b['id'] == _branch)
                    ? _branch : null,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Registration branch *'),
            items: [
              for (final b in _availableBranches)
                DropdownMenuItem<String>(value: b['id'],
                  child: Text(b['name']!, maxLines: 1,
                      overflow: TextOverflow.ellipsis)),
            ],
            onChanged: (v) {
              setState(() => _branch = v);
              _identityEdited();
            },
          )),
      const SizedBox(height: 10),
      SizedBox(height: 52, child: FilledButton.icon(
        key: const Key('register-check-national-id'),
        onPressed: _checkingIdentity || _loadingBranches ||
                _availableBranches.isEmpty ? null : _checkNationalId,
        icon: Icon(_checkingIdentity
            ? Icons.hourglass_top_rounded : Icons.manage_search_rounded),
        label: Text(_checkingIdentity ? 'Checking securely...' : 'Check National ID'),
      )),
      if (_identityMessage != null) Padding(
        padding: const EdgeInsets.only(top: 17),
        child: BfsPanel(child: Row(children: [
          Icon(_identityChecked ? Icons.info_outline : Icons.shield_outlined,
              color: _identityChecked
                  ? BatlokoaDesign.accent : BatlokoaDesign.primary),
          const SizedBox(width: 11),
          Expanded(child: Text(_identityMessage!,
            key: const Key('register-identity-result'),
            style: const TextStyle(fontSize: 13, height: 1.5))),
        ]))),
      if (_possibleExistingIdentity) ...[
        const SizedBox(height: 15),
        OutlinedButton.icon(
          key: const Key('register-find-existing-client'),
          icon: const Icon(Icons.people_alt_outlined),
          label: const Text('Open existing client directory'),
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => StaffClientDirectoryScreen(
                staff: widget.staff, gateway: widget.gateway,
              ),
            ),
          ),
        ),
        const SizedBox(height: 8),
        const Text('Use an authorized client record or refer the identity '
            'for review. Do not start a second registration. No identity '
            'number is copied into a search URL.',
            style: TextStyle(fontSize: 12,
                color: BatlokoaDesign.secondaryInk)),
      ],
      const SizedBox(height: 20),
      const Text('An unmatched ID does not guarantee the client is new. '
          'LoanHub must still verify the identity and approve any future '
          'registration submission.',
          style: TextStyle(fontSize: 12, color: BatlokoaDesign.secondaryInk)),
    ],
  );

  Widget _stage() {
    if (_step == -1) return _identityFirst();
    switch (_step) {
      case 0:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _field('First name', _firstName, validate: _required),
          _extraField('middle_name', 'Middle name (optional)'),
          _field('Last name', _lastName, validate: _required),
          _field('Phone', _phone, validate: _validatePhone,
              type: TextInputType.phone),
          const BfsPanel(child: Text(
            'LoanHub defers client email and temporary password to a '
            'separately approved account activation process.')),
        ]);
      case 1:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _select('gender', 'Gender *',
              {'male': 'Male', 'female': 'Female', 'other': 'Other'}),
          _field('Date of birth', _birthDate, validate: _validateDob,
              hint: 'YYYY-MM-DD'),
          const BfsPanel(child: Text('National ID checked on the first screen. '
              'Return to the ID check to enter a different identity.')),
          _field('Passport number', _passport, sensitive: true),
          const Padding(padding: EdgeInsets.only(bottom: 15),
            child: Text('National ID or passport is required. Identity '
              'matching and legacy record review must be completed in LoanHub.',
              style: TextStyle(color: BatlokoaDesign.secondaryInk,
                  fontSize: 12, height: 1.5))),
          _select('marital_status', 'Marital status', {
            'single': 'Single', 'married': 'Married',
            'divorced': 'Divorced', 'widowed': 'Widowed',
          }),
          _extraField('nationality', 'Nationality'),
          _field('District', _district, validate: _required),
          _extraField('town_or_village', 'Town or village'),
          _extraField('physical_address', 'Physical address', sensitive: true),
        ]);
      case 2:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _select('employment_status', 'Employment status *', {
            'employed': 'Employed', 'self_employed': 'Self-employed',
            'unemployed': 'Unemployed', 'student': 'Student',
            'pensioner': 'Pensioner',
          }),
          _extraField('employment_type', 'Employment type'),
          _extraField('employer_name', 'Employer'),
          _extraField('job_title', 'Job title'),
          _extraField('income_day', 'Salary day (1–31)',
              type: TextInputType.number),
          _field('Monthly income', _income, validate: _validateIncome,
              type: const TextInputType.numberWithOptions(decimal: true)),
          _extraField('salary_date', 'Salary date'),
          const SizedBox(height: 10),
          const BfsPanel(child: Text(
            'LoanHub reserves employer-group links, new employer groups '
            'and government CDAS employee number for a future reviewed phase.')),
          const SizedBox(height: 15),
          CheckboxListTile(
            key: const Key('register-existing-loans'),
            value: _hasExistingLoans,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text('Client has existing loans'),
            onChanged: (v) => setState(() => _hasExistingLoans = v == true),
          ),
          if (_hasExistingLoans) ...[
            _extraField('existing_loan_total',
                'Total existing loan balance (LSL)',
                type: const TextInputType.numberWithOptions(decimal: true)),
            const SizedBox(height: 8),
            for (var i = 0; i < _externalDebt.length; i++) _debtItem(i),
            OutlinedButton.icon(
              onPressed: _externalDebt.length >= 50 ? null : _addDebt,
              icon: const Icon(Icons.add),
              label: const Text('Add external debt'),
            ),
          ],
        ]);
      case 3:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const BfsPanel(child: Text(
            'Banking information is prepared locally. LoanHub determines '
            'supported bank prefixes and routing details during approved '
            'registration; no account details are sent by this preview.')),
          const SizedBox(height: 18),
          _select('bank_name', 'Bank (optional)', {
            'FNB': 'First National Bank',
            'PB': 'Lesotho PostBank',
            'STD': 'Standard Lesotho Bank',
            'NB': 'Nedbank Lesotho',
          }),
          if ((_choice['bank_name'] ?? '').isNotEmpty) ...[
            _extraField('bank_account_holder', 'Account holder',
                sensitive: true),
            _extraField('bank_account_number', 'Bank account number',
                type: TextInputType.number, sensitive: true),
            _select('bank_account_type', 'Account type', {
              'savings': 'Savings', 'cheque': 'Cheque / Current',
            }),
            CheckboxListTile(
              key: const Key('register-salary-account'),
              value: _salaryAccount,
              title: const Text('This is the salary account'),
              controlAffinity: ListTileControlAffinity.leading,
              onChanged: (v) => setState(() => _salaryAccount = v == true),
            ),
          ],
        ]);
      default:
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const BfsPanel(child: Text('Review the collected details and '
              'record the client’s explicit consent. The account is not '
              'created by this preparation-only workflow.')),
          const SizedBox(height: 17),
          Text('Client: ' + _firstName.text.trim() + ' ' +
                  _lastName.text.trim(),
              style: const TextStyle(fontWeight: FontWeight.w800,
                  color: BatlokoaDesign.navy)),
          const SizedBox(height: 9),
          Text('Branch: ' + (_branch == null ? 'Not selected'
              : 'Authorized Batlokoa branch')),
          const SizedBox(height: 9),
          Text('Identity: ' + (_nationalId.text.trim().isNotEmpty
              ? 'National ID provided' : 'Passport provided')),
          const SizedBox(height: 9),
          Text('District: ' + _district.text.trim()),
          const SizedBox(height: 9),
          Text('Existing debts: ' + _externalDebt.length.toString()),
          const SizedBox(height: 9),
          Text('Bank account: ' +
              ((_choice['bank_name'] ?? '').isEmpty
                  ? 'Not provided' : 'Prepared for future verification')),
          const SizedBox(height: 16),
          CheckboxListTile(
            key: const Key('register-profile-consent'),
            value: _shareConsent,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text('Client has explicitly authorized profile sharing'),
            onChanged: (v) => setState(() {
              _shareConsent = v == true; _review = false;
            }),
          ),
          CheckboxListTile(
            key: const Key('register-credit-consent'),
            value: _creditConsent,
            controlAffinity: ListTileControlAffinity.leading,
            title: const Text('Client has explicitly authorized credit checks'),
            onChanged: (v) => setState(() {
              _creditConsent = v == true; _review = false;
            }),
          ),
          const SizedBox(height: 15),
          FilledButton.icon(
            key: const Key('register-review'),
            onPressed: _branch == null ? null : _prepareReview,
            icon: const Icon(Icons.fact_check_outlined),
            label: const Text('Confirm review (no submission)'),
          ),
          if (_review) ...[
            const SizedBox(height: 18),
            BfsPanel(child: Column(
              key: const Key('register-review-summary'),
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('Review ready', style: TextStyle(
                    fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                const Text('Identity and historical duplicates must be '
                    'independently reviewed. This does not create a client '
                    'or initiate a loan.'),
                const SizedBox(height: 12),
                FilledButton.icon(
                  key: const Key('register-server-preflight'),
                  onPressed: _serverBusy ? null : _validateOnServer,
                  icon: const Icon(Icons.verified_user_outlined),
                  label: Text(_serverBusy ? 'Checking...' :
                      'Validate with LoanHub gateway'),
                ),
                if (_serverResult != null)
                  Text(_serverResult!,
                      key: const Key('register-server-result')),
              ],
            )),
          ],
          const SizedBox(height: 16),
          BfsPanel(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('LoanHub registration release status',
                style: TextStyle(fontWeight: FontWeight.w800,
                  color: BatlokoaDesign.navy)),
              const SizedBox(height: 9),
              if (_readinessLoading)
                const LinearProgressIndicator(),
              if (_readinessMessage != null)
                Text(_readinessMessage!,
                  key: const Key('register-release-readiness'),
                  style: const TextStyle(height: 1.5)),
              if (!_readinessLoading && _readinessMessage == null)
                const Text('Release not confirmed. Client creation is disabled.'),
            ],
          )),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            key: const Key('register-save-client'),
            onPressed: _clientWritesReleased && _review && !_savingClient
                ? _saveNewClient : null,
            icon: const Icon(Icons.lock_outline),
            label: Text(_savingClient ? 'Saving client...' :
                'Save client to LoanHub — awaiting release'),
          ),
          if (_clientSaveResult != null)
            Text(_clientSaveResult!, key: const Key('register-save-result')),
        ]);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Register client'),
      backgroundColor: BatlokoaDesign.navy, foregroundColor: Colors.white),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 760),
      child: Column(children: [
        Padding(padding: const EdgeInsets.fromLTRB(18, 14, 18, 8),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Expanded(child: Text('Step ' + (_step + 2).toString() +
                  ' of ' + (_steps.length + 1).toString(),
                  style: const TextStyle(color: BatlokoaDesign.primary,
                      fontWeight: FontWeight.w800))),
              const BfsPill(label: 'PREPARATION ONLY'),
            ]),
            const SizedBox(height: 12),
            LinearProgressIndicator(value: (_step + 2) / (_steps.length + 1),
                minHeight: 5, borderRadius: BorderRadius.circular(8)),
            const SizedBox(height: 15),
            BfsSectionTitle(title: _step == -1 ? 'Check National ID' : _steps[_step],
                subtitle: _step == -1
                  ? 'Check for an existing client before proceeding.'
                  : 'LoanHub registration — one section at a time.'),
          ]),
        ),
        Expanded(child: Form(key: _form,
          child: ListView(
            key: ValueKey(_step),
            padding: BfsResponsive.pagePadding(context),
            children: [_stage()],
          ))),
        Padding(padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Row(children: [
            Expanded(child: OutlinedButton.icon(
              onPressed: _step == -1 || _serverBusy || _checkingIdentity ? null
                  : () => setState(() {
                      _step--; _review = false; _serverResult = null;
                    }),
              icon: const Icon(Icons.chevron_left),
              label: const Text('Previous'),
            )),
            const SizedBox(width: 12),
            Expanded(child: FilledButton.icon(
              key: const Key('register-continue'),
              onPressed: _step == 4 || _loadingBranches ||
                  _serverBusy || _checkingIdentity ||
                  (_step == -1 && !_identityChecked) ? null : _nextStep,
              icon: const Icon(Icons.chevron_right),
              label: Text(_step == -1 ? 'Continue' : _step == 3 ? 'Review' : 'Continue'),
            )),
          ]),
        ),
      ]),
    ))),
  );
}