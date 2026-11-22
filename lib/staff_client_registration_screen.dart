import 'package:flutter/material.dart';
import 'staff_gateway.dart';
import 'batlokoa_design.dart';
import 'bfs_responsive.dart';

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
  int _step = 0;
  static const _steps = [
    'Personal details', 'Identity and address', 'Employment and loans',
    'Banking details', 'Consent and review',
  ];
  final _extra = <String, TextEditingController>{};
  final _choice = <String, String>{
    'marital_status': '', 'employment_type': '',
    'bank_name': '', 'bank_account_type': 'savings',
  };
  bool _hasExistingLoans = false;
  bool _salaryAccount = false;
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
        onChanged: (v) => setState(() => _choice[key] = v ?? ''),
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
  String? _serverResult;

  @override
  void initState() {
    super.initState();
    if (!widget.staff.companyWide && widget.staff.branchIds.length == 1) {
      _branch = widget.staff.branchIds.single;
    }
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
    if (_serverBusy || !_review || _branch == null) return;
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

  @override
  void dispose() {
    for (final controller in [
      _firstName, _lastName, _phone, _birthDate, _nationalId,
      _passport, _district, _income, _gender, _employment,
    ]) {
      controller.dispose();
    }
    for (final controller in _extra.values) { controller.dispose(); }
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
      obscureText: sensitive,
      decoration: InputDecoration(
        labelText: name, hintText: hint,
        border: const OutlineInputBorder(),
      ),
      validator: validate,
      onChanged: (_) { if (_review) setState(() {
        _review = false; _serverResult = null;
      }); },
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Register client'),
      backgroundColor: BatlokoaDesign.navy, foregroundColor: Colors.white),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 760),
      child: Form(key: _form, child: ListView(
        padding: BfsResponsive.pagePadding(context),
        children: [
          Text('Client details', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 8),
          const Text('Preparation only. No client record will be created or changed. '
              'Identity review and release approval are required before submission.'),
          const SizedBox(height: 20),
          if (widget.staff.branchIds.isEmpty)
            const Card(child: Padding(padding: EdgeInsets.all(16),
              child: Text('No verified branch is available for registration. '
                  'Ask your administrator to confirm your branch assignment.'))),
          if (widget.staff.branchIds.isNotEmpty)
            Padding(padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<String>(
                key: const Key('register-branch'),
                value: _branch,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Verified branch', border: OutlineInputBorder()),
                items: [
                  for (final branch in widget.staff.branchIds)
                    DropdownMenuItem(value: branch, child: Text(branch)),
                ],
                onChanged: (value) => setState(() {
                  _branch = value;
                  _review = false;
                }),
                validator: (value) => value == null ? 'Choose a verified branch' : null,
              )),
          _field('First name', _firstName, validate: _required),
          _field('Last name', _lastName, validate: _required),
          _field('Phone', _phone, validate: _validatePhone,
              type: TextInputType.phone),
          _field('Date of birth', _birthDate, validate: _validateDob,
              hint: 'YYYY-MM-DD'),
          _field('Gender', _gender, validate: _required),
          _field('District', _district, validate: _required),
          _field('Employment status', _employment, validate: _required),
          _field('National ID', _nationalId, sensitive: true),
          _field('Passport number', _passport, sensitive: true),
          _field('Monthly income', _income, validate: _validateIncome,
              type: const TextInputType.numberWithOptions(decimal: true)),
          CheckboxListTile(
            key: const Key('register-profile-consent'),
            value: _shareConsent,
            title: const Text('Client has explicitly authorized profile sharing'),
            onChanged: (v) => setState(() {
              _shareConsent = v == true; _review = false;
            }),
          ),
          CheckboxListTile(
            key: const Key('register-credit-consent'),
            value: _creditConsent,
            title: const Text('Client has explicitly authorized credit checks'),
            onChanged: (v) => setState(() {
              _creditConsent = v == true; _review = false;
            }),
          ),
          FilledButton.icon(
            key: const Key('register-review'),
            onPressed: widget.staff.branchIds.isEmpty ? null : _prepareReview,
            icon: const Icon(Icons.fact_check_outlined),
            label: const Text('Review details (no submission)'),
          ),
          if (_review) ...[
            const SizedBox(height: 18),
            Card(key: const Key('register-review-summary'),
              child: Padding(padding: const EdgeInsets.all(18),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Registration review',
                        style: TextStyle(fontWeight: FontWeight.bold)),
                    Text('Client: ${_firstName.text.trim()} ${_lastName.text.trim()}'),
                    Text('Branch: ${_branch ?? ''}'),
                    Text('District: ${_district.text.trim()}'),
                    Text('Profile sharing consent: ${_shareConsent ? 'Yes' : 'No'}'),
                    Text('Credit-check consent: ${_creditConsent ? 'Yes' : 'No'}'),
                    const SizedBox(height: 8),
                    const Text('Identity and legacy-client duplication must be '
                        'independently reviewed. No application, client account '
                        'or loan is created from this screen.'),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      key: const Key('register-server-preflight'),
                      onPressed: _serverBusy ? null : _validateOnServer,
                      icon: const Icon(Icons.verified_user_outlined),
                      label: Text(_serverBusy ? 'Validating...' :
                          'Validate with secure gateway (no submission)'),
                    ),
                    if (_serverResult != null)
                      Text(_serverResult!,
                          key: const Key('register-server-result')),
                  ],
                ))),
          ],
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: null,
            icon: Icon(Icons.lock_outline),
            label: Text('Submit registration — unavailable'),
          ),
        ],
      )),
    ))),
  );
}
