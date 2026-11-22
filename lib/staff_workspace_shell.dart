import 'package:flutter/material.dart';
import 'batlokoa_design.dart';
import 'batlokoa_logo.dart';
import 'staff_gateway.dart';
import 'staff_client_directory_screen.dart';
import 'staff_client_registration_screen.dart';
import 'owner_staff_management_screen.dart';

/// Responsive, authenticated BFS workspace: one purpose per tab.
class StaffWorkspaceShell extends StatefulWidget {
  final StaffSession session;
  final StaffGateway gateway;
  final Future<void> Function() onLogout;
  final bool busy;
  final String? error;
  const StaffWorkspaceShell({super.key, required this.session, required this.gateway,
    required this.onLogout, required this.busy, this.error});
  @override
  State<StaffWorkspaceShell> createState() => _StaffWorkspaceShellState();
}

class _StaffWorkspaceShellState extends State<StaffWorkspaceShell> {
  int tab = 0;
  bool get owner => widget.session.role == 'COMPANY_OWNER' && widget.session.companyWide;
  bool get canManage => owner && widget.gateway is OwnerStaffManagementGateway;

  void open(Widget page) => Navigator.push(context,
    MaterialPageRoute<void>(builder: (_) => page));

  Widget tile(IconData icon, String title, String subtitle, {VoidCallback? onTap, Key? key,
      bool disabled = false}) => Card(
    margin: const EdgeInsets.only(bottom: 12),
    child: ListTile(
      key: key, contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      leading: Container(width: 46, height: 46,
        decoration: BoxDecoration(
          color: disabled ? const Color(0xFFF1F2F5) : const Color(0xFFFFEBED),
          borderRadius: BorderRadius.circular(14)),
        child: Icon(icon, color: disabled ? BatlokoaDesign.silver : BatlokoaDesign.primary)),
      title: Text(title, style: const TextStyle(
        fontWeight: FontWeight.w700, color: BatlokoaDesign.navy)),
      subtitle: Padding(padding: const EdgeInsets.only(top: 4),
        child: Text(subtitle, style: const TextStyle(fontSize: 12, height: 1.5))),
      trailing: Icon(disabled ? Icons.lock_outline : Icons.chevron_right_rounded,
        color: BatlokoaDesign.silver),
      onTap: disabled ? null : onTap,
    ));

  Widget page(String title, String subtitle, List<Widget> children) => ListView(
    padding: const EdgeInsets.fromLTRB(18, 20, 18, 28),
    children: [
      Text(title, style: const TextStyle(fontSize: 27,
        color: BatlokoaDesign.navy, fontWeight: FontWeight.w800)),
      const SizedBox(height: 5),
      Text(subtitle, style: const TextStyle(
        color: BatlokoaDesign.silver, fontSize: 14)),
      const SizedBox(height: 20),
      ...children,
    ]);

  Widget hero() => Container(
    padding: const EdgeInsets.all(22),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(22),
      gradient: const LinearGradient(
        begin: Alignment.topLeft, end: Alignment.bottomRight,
        colors: [BatlokoaDesign.navy, Color(0xFF284B77)])),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Container(width: 29, height: 4,
          decoration: BoxDecoration(color: BatlokoaDesign.primary,
            borderRadius: BorderRadius.circular(3))),
        const SizedBox(width: 9),
        const Text('BFS SECURE WORKSPACE', style: TextStyle(
          fontSize: 10, letterSpacing: 1.4, fontWeight: FontWeight.w800,
          color: Color(0xFFB5D8FF))),
      ]),
      const SizedBox(height: 18),
      Text(owner ? 'Company owner workspace' : 'Employee workspace',
        style: const TextStyle(fontSize: 22,
          fontWeight: FontWeight.w800, color: Colors.white)),
      const SizedBox(height: 8),
      Text(owner
        ? 'Manage Batlokoa across your branches.'
        : 'Your secure, branch-authorized LoanHub workspace.',
        style: const TextStyle(color: Color(0xFFE3EDF9))),
      const SizedBox(height: 18),
      Text(owner ? 'Company-wide staff scope' : 'Verified LoanHub access',
        style: const TextStyle(fontSize: 12, color: Colors.white,
          fontWeight: FontWeight.w600)),
    ]));

  Widget home() => page('Welcome back', BatlokoaDesign.motto, [
    hero(), const SizedBox(height: 22),
    const Text('Quick access', style: TextStyle(fontSize: 18,
      fontWeight: FontWeight.w800, color: BatlokoaDesign.navy)),
    const SizedBox(height: 12),
    tile(Icons.search_rounded, 'Find clients', 'Search authorized LoanHub clients',
      key: const Key('staff-find-clients'),
      onTap: () => open(StaffClientDirectoryScreen(
        gateway: widget.gateway, staff: widget.session))),
    if (canManage)
      tile(Icons.groups_2_outlined, 'Manage employees',
        'Staff directory, branches and registration',
        key: const Key('owner-manage-employees'),
        onTap: () => open(OwnerStaffManagementScreen(
          staff: widget.session,
          gateway: widget.gateway as OwnerStaffManagementGateway))),
    tile(Icons.person_add_alt_outlined, 'Register client',
      'Prepare client details for identity review',
      key: const Key('staff-register-client'),
      onTap: () => open(StaffClientRegistrationScreen(
        staff: widget.session, gateway: widget.gateway))),
    if (widget.error != null) Text(widget.error!,
      style: const TextStyle(color: BatlokoaDesign.primary)),
    const SizedBox(height: 10),
    const Text('No client creation, loan approval or payments are enabled.',
      style: TextStyle(fontSize: 12, color: BatlokoaDesign.silver)),
  ]);

  Widget clients() => page('Clients', 'Client search and identity review', [
    tile(Icons.search_rounded, 'Find clients',
      'Search by client name or account reference',
      onTap: () => open(StaffClientDirectoryScreen(
        gateway: widget.gateway, staff: widget.session))),
    tile(Icons.person_add_alt_outlined, 'Prepare registration',
      'Validate new client identity; submission disabled',
      onTap: () => open(StaffClientRegistrationScreen(
        staff: widget.session, gateway: widget.gateway))),
    tile(Icons.description_outlined, 'Loan applications',
      'Loan submission not yet enabled', disabled: true),
  ]);

  Widget team() => page('Team', 'Employees and company branches', [
    if (canManage)
      tile(Icons.groups_outlined, 'Employee directory',
        'View employees and manage registration',
        onTap: () => open(OwnerStaffManagementScreen(
          staff: widget.session,
          gateway: widget.gateway as OwnerStaffManagementGateway)))
    else
      const Card(child: Padding(padding: EdgeInsets.all(18),
        child: Text('Employee management is restricted to the company owner.'))),
    const SizedBox(height: 10),
    const Text('Employee account creation requires a separate authorized release.',
      style: TextStyle(fontSize: 12, color: BatlokoaDesign.silver)),
  ]);

  Widget account() => page('Account', 'LoanHub role and session', [
    tile(Icons.verified_user_outlined, 'Verified LoanHub access',
      owner ? 'Company-wide staff scope' : 'Assigned branches'),
    Card(child: Padding(padding: const EdgeInsets.all(18),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Session and permissions', style: TextStyle(
          fontWeight: FontWeight.w800, color: BatlokoaDesign.navy)),
        const SizedBox(height: 13),
        Text('Role: ' + widget.session.role.replaceAll('_', ' ')),
        const SizedBox(height: 8),
        Text('Company ID: ' + widget.session.companyId),
        if (owner) ...[
          const SizedBox(height: 10),
          const Text('Company-wide access verified by LoanHub. Financial approvals '
            'and client creation are not enabled in this pilot.'),
        ],
        for (final branch in widget.session.branchIds)
          Text('Branch ID: ' + branch),
      ]))),
    const SizedBox(height: 18),
    FilledButton.icon(
      onPressed: widget.busy ? null : widget.onLogout,
      icon: const Icon(Icons.logout), label: const Text('Sign out securely')),
  ]);

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 820;
    const destinations = <NavigationDestination>[
      NavigationDestination(icon: Icon(Icons.home_outlined),
        selectedIcon: Icon(Icons.home_rounded), label: 'Home'),
      NavigationDestination(icon: Icon(Icons.people_outline),
        selectedIcon: Icon(Icons.people_rounded), label: 'Clients'),
      NavigationDestination(icon: Icon(Icons.badge_outlined),
        selectedIcon: Icon(Icons.badge_rounded), label: 'Team'),
      NavigationDestination(icon: Icon(Icons.person_outline),
        selectedIcon: Icon(Icons.person_rounded), label: 'Account'),
    ];
    final pages = [home(), clients(), team(), account()];
    return Scaffold(
      backgroundColor: BatlokoaDesign.canvas,
      appBar: AppBar(
        backgroundColor: BatlokoaDesign.navy,
        foregroundColor: Colors.white, titleSpacing: 16,
        title: const Row(children: [
          DecoratedBox(decoration: BoxDecoration(color: Colors.white,
            borderRadius: BorderRadius.all(Radius.circular(10))),
            child: Padding(padding: EdgeInsets.all(4), child: BatlokoaLogo(size: 31))),
          SizedBox(width: 10),
          Expanded(child: Text('Batlokoa Financial Services',
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
        ]),
        actions: [IconButton(
          key: const Key('staff-logout'),
          tooltip: 'Sign out', onPressed: widget.busy ? null : widget.onLogout,
          icon: const Icon(Icons.logout_rounded))],
      ),
      body: SafeArea(child: Row(children: [
        if (wide)
          NavigationRail(
            selectedIndex: tab,
            onDestinationSelected: (n) => setState(() => tab = n),
            destinations: const [
              NavigationRailDestination(icon: Icon(Icons.home_outlined), label: Text('Home')),
              NavigationRailDestination(icon: Icon(Icons.people_outline), label: Text('Clients')),
              NavigationRailDestination(icon: Icon(Icons.badge_outlined), label: Text('Team')),
              NavigationRailDestination(icon: Icon(Icons.person_outline), label: Text('Account')),
            ]),
        Expanded(child: Center(child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: IndexedStack(index: tab, children: pages)))),
      ])),
      bottomNavigationBar: wide ? null : NavigationBar(
        key: const Key('staff-bottom-navigation'),
        selectedIndex: tab,
        onDestinationSelected: (n) => setState(() => tab = n),
        destinations: destinations,
      ),
    );
  }
}
