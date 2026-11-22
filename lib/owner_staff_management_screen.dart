import 'package:flutter/material.dart';
import 'batlokoa_design.dart';
import 'staff_gateway.dart';
import 'owner_staff_registration_screen.dart';

/// One focused screen: owner staff roster. Registration is a separate route.
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

  void openRegistration() async {
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) =>
      OwnerStaffRegistrationScreen(staff: widget.staff, gateway: widget.gateway)));
    if (mounted) refresh();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Employees'),
      backgroundColor: BatlokoaDesign.navy,
      foregroundColor: Colors.white,
    ),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 740),
      child: ListView(padding: const EdgeInsets.all(18), children: [
        const Text('Your team', style: TextStyle(
          fontSize: 27, color: BatlokoaDesign.navy,
          fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        const Text('Staff access and branch assignments are managed through LoanHub.',
          style: TextStyle(color: BatlokoaDesign.secondaryInk)),
        const SizedBox(height: 20),
        Card(
          child: Padding(padding: const EdgeInsets.all(16),
            child: Row(children: [
              const Icon(Icons.groups_2_outlined, color: BatlokoaDesign.accent, size: 32),
              const SizedBox(width: 14),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Existing staff (' + members.length.toString() + ')',
                  style: const TextStyle(fontWeight: FontWeight.w800,
                    fontSize: 17, color: BatlokoaDesign.navy)),
                const Text('Review employees and verified status',
                  style: TextStyle(color: BatlokoaDesign.silver, fontSize: 12)),
              ])),
            ])),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          key: const Key('owner-open-register-staff'),
          onPressed: loading || error != null ? null : openRegistration,
          icon: const Icon(Icons.person_add_alt_1_outlined),
          label: const Text('Register employee')),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: loading ? null : refresh,
          icon: const Icon(Icons.refresh),
          label: const Text('Refresh staff')),
        if (loading) const Padding(padding: EdgeInsets.all(18),
          child: Center(child: CircularProgressIndicator())),
        if (error != null) Padding(padding: const EdgeInsets.all(14),
          child: Text(error!, key: const Key('owner-staff-error'),
            style: const TextStyle(color: BatlokoaDesign.primary))),
        const SizedBox(height: 16),
        if (!loading && error == null && members.isEmpty)
          const Card(child: Padding(padding: EdgeInsets.all(20),
            child: Text('No employees returned from your authorized directory.'))),
        if (!loading && error == null)
          for (final person in members)
            Card(child: ListTile(
              leading: const CircleAvatar(backgroundColor: Color(0xFFFFEBED),
                child: Icon(Icons.badge_outlined, color: BatlokoaDesign.primary)),
              title: Text((person['name'] ?? 'Employee').toString(),
                style: const TextStyle(fontWeight: FontWeight.w700)),
              subtitle: Text(
                (person['role'] ?? 'Staff').toString().replaceAll('_',' ') +
                ' · ' + (person['active'] == true ? 'Active' : 'Inactive') +
                ' · ' + (person['verified'] == true ? 'Verified' : 'Pending verification')),
            )),
        const SizedBox(height: 18),
        const Text('New staff accounts require an independent release approval '
          'and LoanHub verification before sign-in.',
          style: TextStyle(fontSize: 12, color: BatlokoaDesign.secondaryInk)),
      ]),
    ))),
  );
}
