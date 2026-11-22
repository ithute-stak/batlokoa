import 'package:flutter/material.dart';
import 'batlokoa_design.dart';
import 'batlokoa_logo.dart';
import 'bfs_widgets.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';
import 'staff_client_directory_screen.dart';
import 'staff_client_registration_screen.dart';
import 'owner_staff_management_screen.dart';

/// Real LoanHub workspace with deliberate, individual destinations.
class StaffWorkspaceShell extends StatefulWidget {
  final StaffSession session;
  final StaffGateway gateway;
  final Future<void> Function() onLogout;
  final bool busy;
  final String? error;
  const StaffWorkspaceShell({super.key, required this.session,
    required this.gateway, required this.onLogout,
    required this.busy, this.error});
  @override
  State<StaffWorkspaceShell> createState() => _StaffWorkspaceShellState();
}

class _StaffWorkspaceShellState extends State<StaffWorkspaceShell> {
  int tab = 0;
  bool get owner => widget.session.role == 'COMPANY_OWNER'
      && widget.session.companyWide;
  bool get canManage => owner && widget.gateway is OwnerStaffManagementGateway;
  void open(Widget screen) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => screen));

  void openClients() => open(StaffClientDirectoryScreen(
    gateway: widget.gateway, staff: widget.session));
  void openReview() => open(StaffClientRegistrationScreen(
    staff: widget.session, gateway: widget.gateway));
  void openTeam() {
    if (!canManage) return;
    open(OwnerStaffManagementScreen(
      staff: widget.session,
      gateway: widget.gateway as OwnerStaffManagementGateway));
  }

  Widget page(Widget header, List<Widget> body) => ListView(
    padding: BfsResponsive.pagePadding(context),
    children: [header, const SizedBox(height: 25), ...body],
  );

  Widget actionGrid(List<Widget> items) => LayoutBuilder(
    builder: (context, constraints) {
      final scale = MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 2.5);
      final available = constraints.maxWidth;
      // A single, compact row per action on small phones. Two or three
      // columns only where actual usable width and text scaling permit it.
      final columns = scale > 1.35 || available < 440
          ? 1 : available < 720 ? 2 : 3;
      if (columns == 1) {
        return Column(children: [
          for (final item in items)
            Padding(padding: const EdgeInsets.only(bottom: 12),
              child: SizedBox(width: double.infinity, child: item)),
        ]);
      }
      return GridView.count(
        crossAxisCount: columns,
        crossAxisSpacing: 12, mainAxisSpacing: 12,
        mainAxisExtent: 187 * scale,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        children: items,
      );
    },
  );

  Widget home() => page(
    const BfsSectionTitle(title: 'Welcome back',
      eyebrow: 'YOUR WORKSPACE', subtitle: BatlokoaDesign.motto), [
    Container(
      padding: const EdgeInsets.all(23),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: const LinearGradient(
          colors: [BatlokoaDesign.navy, Color(0xFF244369)],
          begin: Alignment.topLeft, end: Alignment.bottomRight)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Flexible(child: Align(alignment: Alignment.centerLeft,
            child: BfsPill(label: 'CONNECTED TO LOANHUB',
              color: Colors.white, background: Color(0xFF345475)))),
          SizedBox(width: 8),
          Icon(Icons.shield_outlined, color: Colors.white70),
        ]),
        const SizedBox(height: 27),
        Text(owner ? 'Company owner workspace' : 'Employee workspace',
          style: const TextStyle(color: Colors.white,
            fontSize: 24, height: 1.2, fontWeight: FontWeight.w800)),
        const SizedBox(height: 9),
        Text(owner ? 'Your business, your people, one secure view.'
          : 'Everything you need for your assigned branch.',
          style: const TextStyle(color: Color(0xFFCEDDEA),
            fontSize: 13, height: 1.6)),
        const SizedBox(height: 22),
        Container(width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 13),
          decoration: BoxDecoration(color: const Color(0xFF344F71),
            borderRadius: BorderRadius.circular(13)),
          child: Row(children: [
            const Icon(Icons.verified_user_outlined, size: 18,
              color: Color(0xFFB3D6FF)),
            const SizedBox(width: 9),
            Expanded(child: Text(owner ? 'Company-wide staff scope'
                : 'Verified LoanHub access',
              style: const TextStyle(color: Colors.white,
                fontSize: 12, fontWeight: FontWeight.w700))),
          ])),
      ]),
    ),
    const SizedBox(height: 27),
    Row(children: [
      const Expanded(child: Text('Quick actions', style: TextStyle(
        color: BatlokoaDesign.navy, fontSize: 19,
        fontWeight: FontWeight.w800))),
      TextButton(onPressed: () => setState(() => tab = 1),
        child: const Text('View clients')),
    ]),
    const SizedBox(height: 12),
    actionGrid([
      KeyedSubtree(key: const Key('staff-find-clients'),
        child: BfsActionPanel(icon: Icons.manage_search_rounded,
          title: 'Find clients', description: 'Search LoanHub records',
          primary: true, onPressed: openClients)),
      if (canManage)
        KeyedSubtree(key: const Key('owner-manage-employees'),
          child: BfsActionPanel(icon: Icons.groups_2_outlined,
            title: 'Manage team', description: 'People and branches',
            onPressed: openTeam)),
      KeyedSubtree(key: const Key('staff-register-client'),
        child: BfsActionPanel(icon: Icons.person_add_alt_1_outlined,
          title: 'Register client', description: 'Prepare identity review',
          onPressed: openReview)),
    ]),
    const SizedBox(height: 25),
    const BfsPanel(child: Row(children: [
      Icon(Icons.info_outline, size: 20, color: BatlokoaDesign.accent),
      SizedBox(width: 12),
      Expanded(child: Text('This is a controlled read-only pilot. '
        'Client submission and financial transactions remain disabled.',
        style: TextStyle(fontSize: 12, height: 1.6,
          color: BatlokoaDesign.secondaryInk))),
    ])),
    if (widget.error != null)
      Padding(padding: const EdgeInsets.only(top: 14),
        child: Text(widget.error!,
          style: const TextStyle(color: BatlokoaDesign.primary))),
  ]);

  Widget clients() => page(
    const BfsSectionTitle(eyebrow: 'CUSTOMER SERVICES',
      title: 'Clients', subtitle: 'Find records and prepare identity reviews.'), [
    BfsActionPanel(icon: Icons.manage_search_rounded,
      title: 'Client directory',
      description: 'Search clients by name or account reference',
      primary: true, onPressed: openClients),
    const SizedBox(height: 14),
    BfsActionPanel(icon: Icons.person_add_alt_outlined,
      title: 'New client review',
      description: 'Prepare a client registration for identity checks',
      onPressed: openReview),
    const SizedBox(height: 14),
    const BfsActionPanel(icon: Icons.description_outlined,
      title: 'Loan applications',
      description: 'Application submission is not yet enabled',
      disabled: true),
  ]);

  Widget team() => page(
    const BfsSectionTitle(eyebrow: 'PEOPLE & OPERATIONS',
      title: 'Your team', subtitle: 'A dedicated space for employees.'), [
    if (canManage) ...[
      BfsActionPanel(icon: Icons.groups_outlined,
        title: 'Employee directory',
        description: 'View employees, verification and branches',
        primary: true, onPressed: openTeam),
      const SizedBox(height: 14),
      const BfsPanel(child: Text('Employee registration is a separate screen '
        'and remains subject to authorized LoanHub approval.',
        style: TextStyle(fontSize: 12, height: 1.5,
          color: BatlokoaDesign.silver))),
    ] else
      const BfsPanel(child: Row(children: [
        Icon(Icons.lock_outline, color: BatlokoaDesign.primary),
        SizedBox(width: 12),
        Expanded(child: Text('Staff management is available only to '
          'the company owner.')),
      ])),
  ]);

  Widget account() => page(
    const BfsSectionTitle(eyebrow: 'SECURITY & PREFERENCES',
      title: 'Account', subtitle: 'Your secure LoanHub session.'), [
    BfsPanel(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Row(children: [
        Icon(Icons.verified_user_rounded, color: BatlokoaDesign.accent),
        SizedBox(width: 10),
        Expanded(child: Text('Verified LoanHub access',
          softWrap: true, style: TextStyle(fontSize: 16,
            fontWeight: FontWeight.w800, color: BatlokoaDesign.navy))),
      ]),
      const SizedBox(height: 17),
      Text('Role', style: Theme.of(context).textTheme.labelMedium),
      Text(widget.session.role.replaceAll('_', ' '),
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      const Divider(height: 25),
      Text('Company ID', style: Theme.of(context).textTheme.labelMedium),
      SelectableText(widget.session.companyId),
      const Divider(height: 25),
      Text(owner ? 'Company-wide staff scope' : 'Assigned branches',
        style: const TextStyle(color: BatlokoaDesign.navy,
          fontWeight: FontWeight.w700)),
      for (final branch in widget.session.branchIds)
        Text('Branch ID: ' + branch),
      if (owner) ...[
        const SizedBox(height: 12),
        const Text('Financial approvals and client creation are not enabled '
          'in this pilot.', style: TextStyle(color: BatlokoaDesign.silver,
            height: 1.5)),
      ],
    ])),
    const SizedBox(height: 24),
    SizedBox(height: 52, child: FilledButton.icon(
      onPressed: widget.busy ? null : widget.onLogout,
      icon: const Icon(Icons.logout_rounded),
      label: const Text('Sign out securely'))),
  ]);

  @override
  Widget build(BuildContext context) {
    final availableWidth = MediaQuery.sizeOf(context).width;
    final wide = availableWidth >= 820;

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
    return Scaffold(
      appBar: AppBar(
        backgroundColor: BatlokoaDesign.navy,
        foregroundColor: Colors.white,
        titleSpacing: 17,
        title: const Row(children: [
          DecoratedBox(decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.all(Radius.circular(12))),
            child: Padding(padding: EdgeInsets.all(5),
              child: BatlokoaLogo(size: 33))),
          SizedBox(width: 11),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('BATLOKOA',
                style: TextStyle(fontWeight: FontWeight.w900,
                  letterSpacing: 1.3, fontSize: 15)),
              Text('FINANCIAL SERVICES',
                style: TextStyle(fontWeight: FontWeight.w500,
                  letterSpacing: 1.4, color: Color(0xFFD0DCE9), fontSize: 9)),
            ],
          )),
        ]),
        actions: [IconButton(
          key: const Key('staff-logout'), tooltip: 'Sign out',
          onPressed: widget.busy ? null : widget.onLogout,
          icon: const Icon(Icons.logout_outlined))],
      ),
      body: SafeArea(child: Row(children: [
        if (wide) NavigationRail(selectedIndex: tab,
          onDestinationSelected: (index) => setState(() => tab = index),
          destinations: const [
            NavigationRailDestination(icon: Icon(Icons.home_outlined),
              label: Text('Home')),
            NavigationRailDestination(icon: Icon(Icons.people_outline),
              label: Text('Clients')),
            NavigationRailDestination(icon: Icon(Icons.badge_outlined),
              label: Text('Team')),
            NavigationRailDestination(icon: Icon(Icons.person_outline),
              label: Text('Account')),
          ]),
        Expanded(child: Center(child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 860),
          child: IndexedStack(index: tab,
            children: [home(), clients(), team(), account()])))),
      ])),
      bottomNavigationBar: wide ? null : DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: Color(0xFFE4EAF1)))),
        child: NavigationBar(key: const Key('staff-bottom-navigation'),
          height: BfsResponsive.navigationHeight(context),
          selectedIndex: tab,
          onDestinationSelected: (index) => setState(() => tab = index),
          destinations: destinations)),
    );
  }
}
