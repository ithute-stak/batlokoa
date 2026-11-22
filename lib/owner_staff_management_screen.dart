import 'package:flutter/material.dart';
import 'batlokoa_design.dart';
import 'bfs_widgets.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';
import 'owner_staff_registration_screen.dart';

/// Dedicated, role-scoped staff directory; account creation is another screen.
class OwnerStaffManagementScreen extends StatefulWidget {
  final StaffSession staff;
  final OwnerStaffManagementGateway gateway;
  const OwnerStaffManagementScreen({super.key,
    required this.staff, required this.gateway});

  @override
  State<OwnerStaffManagementScreen> createState() => _OwnerStaffManagementState();
}

class _OwnerStaffManagementState extends State<OwnerStaffManagementScreen> {
  bool loading = true;
  String? error;
  List<Map<String, dynamic>> members = const [];
  @override
  void initState() { super.initState(); refresh(); }

  Future<void> refresh() async {
    if (widget.staff.role != 'COMPANY_OWNER' || !widget.staff.companyWide) {
      setState(() { loading = false; error = 'Company owner access is required'; });
      return;
    }
    setState(() { loading = true; error = null; });
    try {
      final list = await widget.gateway.ownerStaff();
      if (mounted) setState(() { members = list; loading = false; });
    } catch (_) {
      if (mounted) setState(() {
        loading = false;
        error = 'Unable to retrieve authorized employees. Please retry.';
      });
    }
  }

  Future<void> openRegistration() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) =>
      OwnerStaffRegistrationScreen(staff: widget.staff, gateway: widget.gateway)));
    if (mounted) refresh();
  }

  Widget personRow(Map<String, dynamic> person) {
    final name = (person['name'] ?? 'Employee').toString().trim();
    final role = (person['role'] ?? 'Staff').toString().replaceAll('_', ' ');
    final verified = person['verified'] == true;
    final active = person['active'] == true;
    final initials = name.split(RegExp(r'\s+')).where((word) => word.isNotEmpty)
        .take(2).map((word) => word.substring(0, 1).toUpperCase()).join();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: BfsPanel(child: Row(children: [
        CircleAvatar(
          radius: 25, backgroundColor: const Color(0xFFEAF1FF),
          child: Text(initials.isEmpty ? 'B' : initials, style: const TextStyle(
            color: BatlokoaDesign.navy, fontWeight: FontWeight.w800, fontSize: 15))),
        const SizedBox(width: 13),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(name, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800,
              color: BatlokoaDesign.navy, fontSize: 15)),
          const SizedBox(height: 3),
          Text(role, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, color: BatlokoaDesign.silver)),
          const SizedBox(height: 8),
          Wrap(spacing: 6, runSpacing: 6, children: [
            BfsPill(label: active ? 'Active' : 'Inactive',
              color: active ? const Color(0xFF087B65) : BatlokoaDesign.silver,
              background: active ? const Color(0xFFE7F8F2)
                : const Color(0xFFF2F3F5)),
            BfsPill(label: verified ? 'Verified' : 'Pending verification',
              color: verified ? BatlokoaDesign.accent : const Color(0xFF955B00),
              background: verified ? const Color(0xFFECF3FF)
                : const Color(0xFFFFF2D9)),
          ]),
        ])),
      ])),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Employees'),
      backgroundColor: BatlokoaDesign.navy, foregroundColor: Colors.white),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 740),
      child: ListView(padding: BfsResponsive.pagePadding(context), children: [
        const BfsSectionTitle(eyebrow: 'PEOPLE & PERMISSIONS',
          title: 'Your team',
          subtitle: 'View employees securely across your Batlokoa branches.'),
        const SizedBox(height: 23),
        Container(padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(color: BatlokoaDesign.navy,
            borderRadius: BorderRadius.circular(21)),
          child: Row(children: [
            const Icon(Icons.groups_2_rounded, color: Colors.white, size: 35),
            const SizedBox(width: 17),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(members.length.toString(), style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w800, fontSize: 32)),
                const Text('EMPLOYEES', style: TextStyle(
                  fontSize: 11, color: Color(0xFFCFDCEB), letterSpacing: 1.1)),
              ])),
          ])),
        const SizedBox(height: 17),
        SizedBox(height: 52, child: FilledButton.icon(
          key: const Key('owner-open-register-staff'),
          onPressed: loading || error != null ? null : openRegistration,
          icon: const Icon(Icons.person_add_alt_1_rounded),
          label: const Text('Register employee'))),
        const SizedBox(height: 22),
        Row(children: [
          const Expanded(child: Text('Employee directory', style: TextStyle(
            fontSize: 18, fontWeight: FontWeight.w800,
            color: BatlokoaDesign.navy))),
          IconButton(onPressed: loading ? null : refresh,
            tooltip: 'Refresh employees', icon: const Icon(Icons.refresh_rounded)),
        ]),
        const SizedBox(height: 12),
        if (loading) const Center(child: Padding(
          padding: EdgeInsets.all(25), child: CircularProgressIndicator())),
        if (error != null) BfsPanel(child: Text(error!,
          key: const Key('owner-staff-error'),
          style: const TextStyle(color: BatlokoaDesign.primary))),
        if (!loading && error == null && members.isEmpty)
          const BfsPanel(child: Text('No employees returned from your authorized directory.')),
        if (!loading && error == null)
          for (final person in members) personRow(person),
        const SizedBox(height: 12),
        const Text('Staff registration and account verification are '
          'controlled by LoanHub.', style: TextStyle(
            fontSize: 12, color: BatlokoaDesign.silver, height: 1.5)),
      ]),
    ))),
  );
}
