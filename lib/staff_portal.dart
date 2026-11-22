import 'package:flutter/material.dart';
import 'batlokoa_logo.dart';
import 'staff_gateway.dart';
import 'staff_client_directory_screen.dart';
import 'owner_staff_management_screen.dart';
import 'staff_workspace_shell.dart';
import 'bfs_responsive.dart';
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
  Widget build(BuildContext context) {
    if (!_loading && _session != null) {
      return StaffWorkspaceShell(
        session: _session!, gateway: widget.gateway,
        busy: _busy, error: _error, onLogout: _logout,
      );
    }
    const navy = Color(0xFF12233F);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: navy,
        foregroundColor: Colors.white,
        titleSpacing: 0,
        leading: const BackButton(color: Colors.white),
        title: const Row(children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white, borderRadius: BorderRadius.all(Radius.circular(10)),
            ),
            child: Padding(
              padding: EdgeInsets.all(4),
              child: BatlokoaLogo(size: 31),
            ),
          ),
          SizedBox(width: 12),
          Expanded(
            child: Text('Batlokoa Financial Services',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
            ),
          ),
        ]),
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 620),
            child: _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: BfsResponsive.pagePadding(context),
                  children: [
                    if (_session == null) _signIn(context)
                    else _dashboard(context, _session!),
                  ],
                ),
          ),
        ),
      ),
    );
  }

  Widget _signIn(BuildContext context) {
    const navy = Color(0xFF12233F);
    const red = Color(0xFFD71920);
    const blue = Color(0xFF075EB6);
    return Form(
      key: _form,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            color: navy,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Row(children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
              ),
              child: const BatlokoaLogo(size: 66),
            ),
            const SizedBox(width: 14),
            const Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Batlokoa Financial Services',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800,
                    color: Colors.white)),
                SizedBox(height: 5),
                Text('We make Your Debt Affordable.',
                  style: TextStyle(fontSize: 12, color: Color(0xFFE2EAF8))),
                SizedBox(height: 8),
                Text('SECURE STAFF ACCESS',
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800,
                    letterSpacing: 1, color: Color(0xFF94C5FF))),
              ]),
            ),
          ]),
        ),
        const SizedBox(height: 20),
        Text('Employee sign in',
          style: Theme.of(context).textTheme.headlineMedium?.copyWith(
            fontSize: 26, color: navy, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 4),
        const Text(
          'Company owners and employees use their existing LoanHub accounts.',
          style: TextStyle(fontSize: 13, color: Color(0xFF667085)),
        ),
        const SizedBox(height: 16),
        TextFormField(
          key: const Key('staff-phone'), controller: _phone,
          keyboardType: TextInputType.phone,
          textInputAction: TextInputAction.next,
          autofillHints: const [AutofillHints.telephoneNumber],
          decoration: const InputDecoration(
            labelText: 'LoanHub phone number',
            prefixIcon: Icon(Icons.phone_outlined, color: blue),
          ),
          validator: (value) => value == null || value.trim().length < 8
              ? 'Enter your registered phone number' : null,
        ),
        const SizedBox(height: 12),
        TextFormField(
          key: const Key('staff-password'),
          controller: _password,
          obscureText: _hidePassword,
          autofillHints: const [AutofillHints.password],
          textInputAction: TextInputAction.done,
          onFieldSubmitted: (_) => _login(),
          decoration: InputDecoration(
            labelText: 'Password',
            prefixIcon: const Icon(Icons.lock_outline, color: blue),
            suffixIcon: IconButton(
              tooltip: _hidePassword ? 'Show password' : 'Hide password',
              onPressed: () => setState(() => _hidePassword = !_hidePassword),
              icon: Icon(_hidePassword
                  ? Icons.visibility_outlined : Icons.visibility_off_outlined),
            ),
          ),
          validator: (value) => value == null || value.length < 6
              ? 'Enter your password' : null,
        ),
        const SizedBox(height: 12),
        TextFormField(
          key: const Key('staff-second-factor'),
          controller: _secondFactor,
          obscureText: _useRecoveryCode,
          keyboardType: _useRecoveryCode
              ? TextInputType.text : TextInputType.number,
          decoration: InputDecoration(
            labelText: _useRecoveryCode
              ? 'Recovery code (optional)' : 'Authenticator code (optional)',
            prefixIcon: const Icon(Icons.verified_user_outlined, color: blue),
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
              ? 'Use authenticator code' : 'Use recovery code instead'),
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!, key: const Key('staff-error'),
            style: TextStyle(
              fontSize: 13, color: Theme.of(context).colorScheme.error)),
          const SizedBox(height: 8),
        ],
        const SizedBox(height: 10),
        FilledButton.icon(
          key: const Key('staff-login'),
          style: FilledButton.styleFrom(
            backgroundColor: red,
            minimumSize: const Size.fromHeight(52),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(13)),
          ),
          onPressed: _busy ? null : _login,
          icon: const Icon(Icons.login),
          label: Text(_busy ? 'Verifying...' : 'Sign in securely',
            style: const TextStyle(fontWeight: FontWeight.w700)),
        ),
        const SizedBox(height: 16),
        const Text(
          'Your company and branch permissions are checked securely with LoanHub. '
          'Client creation and financial operations remain disabled in this pilot.',
          style: TextStyle(fontSize: 12, color: Color(0xFF667085)),
        ),
      ]),
    );
  }

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
        if (session.role == 'COMPANY_OWNER' &&
            session.companyWide && widget.gateway is OwnerStaffManagementGateway)
          Card(child: ListTile(
            key: const Key('owner-manage-employees'),
            leading: const Icon(Icons.admin_panel_settings_outlined),
            title: const Text('Manage employees'),
            subtitle: const Text('View staff, assign branches and prepare new employee accounts'),
            trailing: const Icon(Icons.chevron_right),
            onTap: _busy ? null : () => Navigator.push(context,
              MaterialPageRoute<void>(builder: (_) => OwnerStaffManagementScreen(
                staff: session,
                gateway: widget.gateway as OwnerStaffManagementGateway,
              ))),
          )),
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
