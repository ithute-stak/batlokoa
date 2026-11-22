import 'package:flutter/material.dart';
import 'batlokoa_logo.dart';
import 'staff_gateway.dart';
import 'staff_client_directory_screen.dart';
import 'staff_client_registration_screen.dart';

/// Separate staff experience; customer demo state is never reused.
class StaffPortal extends StatefulWidget {
  final StaffGateway gateway;
  const StaffPortal({super.key, this.gateway = const DisabledStaffGateway()});

  @override
  State<StaffPortal> createState() => _StaffPortalState();
}

class _StaffPortalState extends State<StaffPortal> {
  final _form = GlobalKey<FormState>();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _secondFactor = TextEditingController();
  bool _useRecoveryCode = false;
  StaffSession? _session;
  bool _loading = true;
  bool _busy = false;
  bool _hidePassword = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    try {
      final session = await widget.gateway.session();
      if (mounted) setState(() => _session = session);
    } catch (_) {
      if (mounted) setState(() => _error = 'Unable to verify staff session');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _login() async {
    if (!_form.currentState!.validate() || _busy) return;
    setState(() { _busy = true; _error = null; });
    try {
      final enteredSecondFactor = _secondFactor.text.trim();
      final session = widget.gateway is StaffSecondFactorGateway
          ? await (widget.gateway as StaffSecondFactorGateway)
              .loginWithSecondFactor(
                  _phone.text.trim(), _password.text,
                  otp: enteredSecondFactor.isNotEmpty && !_useRecoveryCode
                      ? enteredSecondFactor : null,
                  recoveryCode: enteredSecondFactor.isNotEmpty && _useRecoveryCode
                      ? enteredSecondFactor : null)
          : await widget.gateway.login(_phone.text.trim(), _password.text);
      if (mounted) {
        setState(() => _session = session);
        _password.clear();
        _secondFactor.clear();
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error =
            'Sign-in unavailable or denied. Check your LoanHub account.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _logout() async {
    setState(() { _busy = true; _error = null; });
    try {
      await widget.gateway.logout();
      if (mounted) setState(() => _session = null);
    } catch (_) {
      if (mounted) setState(() => _error =
          'Secure sign-out was not completed. Please retry.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    _secondFactor.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Row(children: [BatlokoaLogo(size: 36), SizedBox(width: 10), Expanded(child: Text('Batlokoa Staff'))]),
        leading: const BackButton()),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 650),
      child: _loading
          ? const CircularProgressIndicator()
          : ListView(padding: const EdgeInsets.all(24), children: [
              if (_session == null) _signIn(context)
              else _dashboard(context, _session!),
            ]),
    ))),
  );

  Widget _signIn(BuildContext context) => Form(
    key: _form,
    child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const Center(child: BatlokoaLogo(size: 96)),
      const SizedBox(height: 16),
      Text('Employee sign in',
          style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 6),
      const Text('Batlokoa Financial Services — use your existing LoanHub employee account. '
          'Branch and permissions are verified automatically.'),
      const SizedBox(height: 24),
      TextFormField(
        key: const Key('staff-phone'), controller: _phone,
        keyboardType: TextInputType.phone,
        textInputAction: TextInputAction.next,
        decoration: const InputDecoration(
          labelText: 'LoanHub phone number',
          prefixIcon: Icon(Icons.phone_outlined)),
        validator: (v) => (v == null || v.trim().length < 8)
            ? 'Enter your registered phone number' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        key: const Key('staff-password'), controller: _password,
        obscureText: _hidePassword,
        textInputAction: TextInputAction.done,
        onFieldSubmitted: (_) => _login(),
        decoration: InputDecoration(labelText: 'Password',
            prefixIcon: const Icon(Icons.lock_outline),
            suffixIcon: IconButton(
              tooltip: _hidePassword ? 'Show password' : 'Hide password',
              onPressed: () => setState(() => _hidePassword = !_hidePassword),
              icon: Icon(_hidePassword
                  ? Icons.visibility_outlined : Icons.visibility_off_outlined))),
        validator: (v) => (v == null || v.length < 6)
            ? 'Enter your password' : null,
      ),
      const SizedBox(height: 12),
      TextFormField(
        key: const Key('staff-second-factor'),
        controller: _secondFactor,
        obscureText: _useRecoveryCode,
        keyboardType: _useRecoveryCode ? TextInputType.text : TextInputType.number,
        textInputAction: TextInputAction.done,
        decoration: InputDecoration(
          labelText: _useRecoveryCode
              ? 'Recovery code (if required)'
              : 'Authenticator code (if required)',
          prefixIcon: const Icon(Icons.verified_user_outlined),
          helperText: 'Leave blank unless LoanHub requires additional verification.',
        ),
        validator: (value) {
          final code = value?.trim() ?? '';
          if (code.isEmpty) return null;
          if (_useRecoveryCode) {
            return code.length >= 8 && code.length <= 32
                ? null : 'Enter a valid recovery code';
          }
          return RegExp(r'^\d{6,8}$').hasMatch(code)
              ? null : 'Enter a 6–8 digit authenticator code';
        },
      ),
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton(
          onPressed: _busy ? null : () => setState(() {
            _useRecoveryCode = !_useRecoveryCode;
            _secondFactor.clear();
          }),
          child: Text(_useRecoveryCode
              ? 'Use authenticator code instead'
              : 'Use a recovery code instead'),
        ),
      ),
      if (_error != null) ...[
        const SizedBox(height: 14),
        Text(_error!, key: const Key('staff-error'),
            style: TextStyle(color: Theme.of(context).colorScheme.error)),
      ],
      const SizedBox(height: 22),
      FilledButton.icon(
        key: const Key('staff-login'),
        onPressed: _busy ? null : _login,
        icon: const Icon(Icons.login),
        label: Text(_busy ? 'Verifying...' : 'Sign in securely'),
      ),
      const SizedBox(height: 12),
      const Text('Staff financial operations remain unavailable '
          'until LoanHub integration is approved.'),
    ]),
  );

  Widget _dashboard(BuildContext context, StaffSession session) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          const BatlokoaLogo(size: 48),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(session.role == 'COMPANY_OWNER'
                  ? 'Company owner workspace' : 'Employee workspace',
                  style: Theme.of(context).textTheme.headlineSmall),
              Text('Role: ${session.role.replaceAll('_', ' ')}'),
            ],
          )),
          IconButton(
            key: const Key('staff-logout'),
            onPressed: _busy ? null : _logout,
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout)),
        ]),
        if (session.role == 'COMPANY_OWNER' && session.companyWide)
          const Card(child: Padding(
            padding: EdgeInsets.all(16),
            child: Text('Company-wide access verified by LoanHub. '
                'Financial approvals and client creation are not enabled in this pilot.'),
          )),
        const SizedBox(height: 20),
        Card(child: Padding(padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Verified LoanHub access',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text('Company ID: ${session.companyId}'),
              Text(session.companyWide
                  ? 'Company-wide staff scope'
                  : 'Assigned branches: ${session.branchIds.length}'),
              for (final branch in session.branchIds)
                Text('Branch ID: $branch'),
            ]),
        )),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
        const SizedBox(height: 16),
        const Text('Operations',
            style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        Card(child: ListTile(
          key: const Key('staff-find-clients'),
          leading: const Icon(Icons.people_outline),
          title: const Text('Find clients'),
          subtitle: const Text('Search your authorized LoanHub client directory'),
          trailing: const Icon(Icons.chevron_right),
          onTap: _busy ? null : () => Navigator.push(
            context,
            MaterialPageRoute<void>(builder: (_) =>
                StaffClientDirectoryScreen(
                  gateway: widget.gateway, staff: session)),
          ),
        )),
        Card(child: ListTile(
          key: const Key('staff-register-client'),
          leading: const Icon(Icons.person_add_alt_outlined),
          title: const Text('Register client'),
          subtitle: const Text('Prepare client details for identity review; no submission'),
          trailing: const Icon(Icons.chevron_right),
          onTap: _busy ? null : () => Navigator.push(
            context, MaterialPageRoute<void>(
              builder: (_) => StaffClientRegistrationScreen(staff: session, gateway: widget.gateway),
            ),
          ),
        )),
        for (final item in const [
          (Icons.description_outlined, 'New loan application',
            'Application submission not yet enabled'),
          (Icons.request_quote_outlined, 'Prepare loan offer',
            'LoanHub offer integration pending'),
        ])
          Card(child: ListTile(
            leading: Icon(item.$1),
            title: Text(item.$2),
            subtitle: Text(item.$3),
            trailing: const Icon(Icons.lock_outline),
            enabled: false,
          )),
        const SizedBox(height: 12),
        const Text('No client, loan or payment data is simulated '
            'in the employee workspace.'),
      ]);
}
