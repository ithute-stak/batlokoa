import 'package:flutter/material.dart';
import 'staff_gateway.dart';
import 'batlokoa_design.dart';
import 'bfs_widgets.dart';

/// Owner-only employee management; never grants client or lending write rights.
class OwnerStaffRegistrationScreen extends StatefulWidget {
  final StaffSession staff;
  final OwnerStaffManagementGateway gateway;
  const OwnerStaffRegistrationScreen({super.key, required this.staff, required this.gateway});

  @override
  State<OwnerStaffRegistrationScreen> createState() => _OwnerStaffRegistrationScreenState();
}

class _OwnerStaffRegistrationScreenState extends State<OwnerStaffRegistrationScreen> {
  final _form = GlobalKey<FormState>();
  final _first = TextEditingController();
  final _last = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String _role = 'LOAN_OFFICER';
  String? _branch;
  bool _confirmed = false;
  bool _loading = true;
  bool _creating = false;
  String? _error;
  String? _success;
  List<Map<String, dynamic>> _branches = const [];

  static const roles = <String, String>{
    'LOAN_OFFICER': 'Loan Officer',
    'BRANCH_MANAGER': 'Branch Manager',
    'CREDIT_ANALYST': 'Credit Analyst',
    'COLLECTIONS_OFFICER': 'Collections Officer',
    'FINANCE_OFFICER': 'Finance Officer',
    'COMPANY_ADMIN': 'Company Administrator',
  };
  bool get needsBranch => _role != 'COMPANY_ADMIN';

  @override
  void initState() { super.initState(); _refresh(); }

  Future<void> _refresh() async {
    if (widget.staff.role != 'COMPANY_OWNER' || !widget.staff.companyWide) {
      setState(() { _error = 'Company owner access is required'; _loading = false; });
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      final branches = await widget.gateway.ownerBranches();
      if (!mounted) return;
      setState(() {
        _branches = branches;
        if (!_branches.any((item) => item['id'] == _branch)) _branch = null;
        _loading = false;
      });
    } catch (_) {
      if (mounted) setState(() {
        _loading = false;
        _error = 'Staff list is unavailable. Check your session and retry.';
      });
    }
  }

  Future<void> _submit() async {
    if (_creating || !_form.currentState!.validate()) return;
    if (!_confirmed) {
      setState(() => _error = 'Confirm the employee identity, role and branch.');
      return;
    }
    setState(() { _creating = true; _error = null; _success = null; });
    try {
      final id = await widget.gateway.createStaffAccount({
        'first_name': _first.text.trim(),
        'last_name': _last.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim().isEmpty ? null : _email.text.trim(),
        'password': _password.text,
        'role': _role,
        'branch_id': needsBranch ? _branch : null,
        'confirm': true,
      });
      if (!mounted) return;
      _first.clear(); _last.clear(); _phone.clear(); _email.clear();
      _password.clear();
      setState(() {
        _confirmed = false;
        _role = 'LOAN_OFFICER';
        _branch = null;
        _success = 'Employee account created: ' + id +
            '. The new employee needs authorized LoanHub account verification '
            'before signing into Batlokoa.';
      });
      await _refresh();
    } catch (error) {
      if (mounted) setState(() => _error = error is StateError
          ? error.message.toString()
          : 'Employee account registration was not confirmed.');
    } finally {
      _password.clear();
      if (mounted) setState(() => _creating = false);
    }
  }

  @override
  void dispose() {
    _first.dispose(); _last.dispose(); _phone.dispose();
    _email.dispose(); _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Register employee'),
        backgroundColor: BatlokoaDesign.navy, foregroundColor: Colors.white),
      body: SafeArea(child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: ListView(padding: const EdgeInsets.all(20), children: [
          const BfsSectionTitle(eyebrow: 'PEOPLE & ACCESS',
            title: 'New employee account',
            subtitle: 'Set up a team member and assign their LoanHub permissions.'),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Text(_error!, key: const Key('owner-staff-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error))),
          if (_success != null) Text(_success!, key: const Key('owner-staff-success')),
          const SizedBox(height: 21),
          const BfsPanel(child: Row(children: [
            Icon(Icons.verified_user_outlined,
              color: BatlokoaDesign.accent, size: 24),
            SizedBox(width: 12),
            Expanded(child: Text('Employee creation is available only '
              'after separate LoanHub approval and owner verification.',
              style: TextStyle(color: BatlokoaDesign.silver,
                height: 1.5, fontSize: 12))),
          ])),
          const SizedBox(height: 23),
          Form(key: _form, child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const _FormSection(number: '01', title: 'Personal details',
                subtitle: 'Details must match the employee identity.'),
              const SizedBox(height: 16),
              TextFormField(key: const Key('staff-first-name'),
                controller: _first, textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'First name',
                  prefixIcon: Icon(Icons.person_outline)),
                validator: (v) => v == null || v.trim().isEmpty ? 'First name required' : null),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-last-name'),
                controller: _last, textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Last name',
                  prefixIcon: Icon(Icons.person_outline)),
                validator: (v) => v == null || v.trim().isEmpty ? 'Last name required' : null),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-phone-number'),
                controller: _phone, keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Employee phone number',
                  prefixIcon: Icon(Icons.phone_outlined)),
                validator: (v) => RegExp(r'^\+?[0-9]{8,15}$').hasMatch(v?.trim() ?? '')
                    ? null : 'Enter a valid phone number'),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-email'),
                controller: _email, keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Email (optional)',
                  prefixIcon: Icon(Icons.mail_outline)),
                validator: (v) => v == null || v.trim().isEmpty ||
                    (v.contains('@') && v.contains('.')) ? null : 'Invalid email'),
              const SizedBox(height: 28),
              const _FormSection(number: '02', title: 'Permissions',
                subtitle: 'Assign the correct role and branch.'),
              const SizedBox(height: 17),
              DropdownButtonFormField<String>(
                key: const Key('staff-role'), value: _role,
                decoration: const InputDecoration(labelText: 'Role'),
                items: [
                  for (final role in roles.entries)
                    DropdownMenuItem(value: role.key, child: Text(role.value)),
                ],
                onChanged: _creating ? null : (v) => setState(() {
                  if (v != null) _role = v;
                  _branch = null;
                }),
              ),
              const SizedBox(height: 10),
              if (needsBranch) ...[
                DropdownButtonFormField<String>(
                  key: const Key('staff-branch'), value: _branch,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Assigned branch'),
                  items: [
                    for (final item in _branches)
                      DropdownMenuItem<String>(
                        value: item['id'] as String,
                        child: Text(item['name'].toString())),
                  ],
                  onChanged: _creating ? null : (v) => setState(() => _branch = v),
                  validator: (v) => v == null ? 'Select a branch' : null,
                ),
                const SizedBox(height: 10),
              ],
              const SizedBox(height: 24),
              const _FormSection(number: '03', title: 'Account security',
                subtitle: 'Use a unique initial password.'),
              const SizedBox(height: 15),
              TextFormField(key: const Key('staff-initial-password'),
                controller: _password, obscureText: true,
                autocorrect: false, enableSuggestions: false,
                decoration: const InputDecoration(labelText: 'Initial password',
                  prefixIcon: Icon(Icons.lock_outline),
                  helperText: 'Share it privately. Never reuse another account password.'),
                validator: (v) => v == null || v.length < 8
                    ? 'Minimum 8 characters' : null),
              const SizedBox(height: 20),
              CheckboxListTile(key: const Key('staff-confirm'),
                value: _confirmed,
                contentPadding: EdgeInsets.zero,
                title: const Text('I confirm this employee, their role and branch.'),
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: _creating ? null : (v) =>
                    setState(() => _confirmed = v ?? false)),
              const SizedBox(height: 18),
              SizedBox(height: 54, child: FilledButton.icon(
                key: const Key('owner-create-staff'),
                onPressed: _loading || _creating ? null : _submit,
                icon: const Icon(Icons.person_add_alt_1),
                label: Text(_creating ? 'Registering...' : 'Register employee'))),
            ],
          )),
        ]),
      ))),
    );
  }
}

class _FormSection extends StatelessWidget {
  final String number, title, subtitle;
  const _FormSection({required this.number, required this.title,
    required this.subtitle});

  @override
  Widget build(BuildContext context) => Row(children: [
    Container(width: 39, height: 39, alignment: Alignment.center,
      decoration: BoxDecoration(color: BatlokoaDesign.navy,
        borderRadius: BorderRadius.circular(12)),
      child: Text(number, style: const TextStyle(color: Colors.white,
        fontWeight: FontWeight.w800, fontSize: 13))),
    const SizedBox(width: 12),
    Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(color: BatlokoaDesign.navy,
        fontWeight: FontWeight.w800, fontSize: 17)),
      const SizedBox(height: 3),
      Text(subtitle, style: const TextStyle(color: BatlokoaDesign.silver,
        fontSize: 12)),
    ])),
  ]);
}
