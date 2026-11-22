import 'package:flutter/material.dart';
import 'staff_gateway.dart';

/// Owner-only employee management; never grants client or lending write rights.
class OwnerStaffManagementScreen extends StatefulWidget {
  final StaffSession staff;
  final OwnerStaffManagementGateway gateway;
  const OwnerStaffManagementScreen({super.key, required this.staff, required this.gateway});

  @override
  State<OwnerStaffManagementScreen> createState() => _OwnerStaffManagementScreenState();
}

class _OwnerStaffManagementScreenState extends State<OwnerStaffManagementScreen> {
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
  List<Map<String, dynamic>> _members = const [];

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
      final members = await widget.gateway.ownerStaff();
      if (!mounted) return;
      setState(() {
        _branches = branches;
        _members = members;
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
    const navy = Color(0xFF12233F);
    return Scaffold(
      appBar: AppBar(title: const Text('Manage employees'),
        backgroundColor: navy, foregroundColor: Colors.white),
      body: SafeArea(child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 720),
        child: ListView(padding: const EdgeInsets.all(18), children: [
          Text('Batlokoa employees',
            style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 5),
          const Text('Owner-only employee management. All roles and branches '
              'are checked against LoanHub.'),
          if (_loading) const LinearProgressIndicator(),
          if (_error != null) Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Text(_error!, key: const Key('owner-staff-error'),
              style: TextStyle(color: Theme.of(context).colorScheme.error))),
          if (_success != null) Text(_success!, key: const Key('owner-staff-success')),
          OutlinedButton.icon(onPressed: _loading ? null : _refresh,
            icon: const Icon(Icons.refresh), label: const Text('Refresh employees')),
          const SizedBox(height: 16),
          Text('Existing staff', style: Theme.of(context).textTheme.titleLarge),
          if (!_loading && _members.isEmpty && _error == null)
            const Text('No employee records returned.'),
          for (final person in _members)
            Card(child: ListTile(
              leading: const Icon(Icons.badge_outlined),
              title: Text((person['name'] ?? 'Employee').toString()),
              subtitle: Text((roles[person['role']] ?? person['role']).toString()
                + ' · ' + (person['active'] == true ? 'Active' : 'Inactive')
                + ' · ' + (person['verified'] == true ? 'Verified' : 'Verification pending')),
            )),
          const SizedBox(height: 18),
          Text('Register an employee',
            style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 6),
          const Text('Account creation requires separate release approval '
            'and a verified owner account. This pilot may permit viewing '
            'employees while account creation is unavailable.',
            style: TextStyle(color: Color(0xFF667085))),
          const SizedBox(height: 12),
          Form(key: _form, child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(key: const Key('staff-first-name'),
                controller: _first, decoration: const InputDecoration(labelText: 'First name'),
                validator: (v) => v == null || v.trim().isEmpty ? 'First name required' : null),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-last-name'),
                controller: _last, decoration: const InputDecoration(labelText: 'Last name'),
                validator: (v) => v == null || v.trim().isEmpty ? 'Last name required' : null),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-phone-number'),
                controller: _phone, keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Employee phone number'),
                validator: (v) => RegExp(r'^\+?[0-9]{8,15}$').hasMatch(v?.trim() ?? '')
                    ? null : 'Enter a valid phone number'),
              const SizedBox(height: 10),
              TextFormField(key: const Key('staff-email'),
                controller: _email, keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Email (optional)'),
                validator: (v) => v == null || v.trim().isEmpty ||
                    (v.contains('@') && v.contains('.')) ? null : 'Invalid email'),
              const SizedBox(height: 10),
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
              TextFormField(key: const Key('staff-initial-password'),
                controller: _password, obscureText: true,
                autocorrect: false, enableSuggestions: false,
                decoration: const InputDecoration(labelText: 'Initial password',
                  helperText: 'Use a unique password, communicated privately.'),
                validator: (v) => v == null || v.length < 8
                    ? 'Minimum 8 characters' : null),
              const SizedBox(height: 8),
              CheckboxListTile(key: const Key('staff-confirm'),
                value: _confirmed,
                contentPadding: EdgeInsets.zero,
                title: const Text('I confirm this employee, their role and branch.'),
                controlAffinity: ListTileControlAffinity.leading,
                onChanged: _creating ? null : (v) =>
                    setState(() => _confirmed = v ?? false)),
              const SizedBox(height: 10),
              FilledButton.icon(
                key: const Key('owner-create-staff'),
                onPressed: _loading || _creating ? null : _submit,
                icon: const Icon(Icons.person_add_alt_1),
                label: Text(_creating ? 'Registering...' : 'Register employee')),
            ],
          )),
        ]),
      ))),
    );
  }
}
