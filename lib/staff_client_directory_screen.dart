import 'package:flutter/material.dart';

import 'staff_gateway.dart';
import 'batlokoa_design.dart';
import 'bfs_widgets.dart';

/// Employee-only, read-only directory; no registration or loan writer here.
class StaffClientDirectoryScreen extends StatefulWidget {
  final StaffGateway gateway;
  final StaffSession staff;
  const StaffClientDirectoryScreen({
    super.key, required this.gateway, required this.staff,
  });

  @override
  State<StaffClientDirectoryScreen> createState() =>
      _StaffClientDirectoryScreenState();
}

class _StaffClientDirectoryScreenState extends State<StaffClientDirectoryScreen> {
  final _search = TextEditingController();
  List<StaffClient> _clients = const [];
  bool _busy = false;
  String? _error;
  String? _selectedBranch;
  int _requestSequence = 0;

  @override
  void initState() {
    super.initState();
    if (!widget.staff.companyWide && widget.staff.branchIds.length == 1) {
      _selectedBranch = widget.staff.branchIds.single;
    }
    _load();
  }

  Future<void> _load() async {
    if (_busy) return;
    final sequence = ++_requestSequence;
    setState(() {
      _busy = true;
      _error = null;
      _clients = const [];
    });
    try {
      final result = await widget.gateway.findClients(
        search: _search.text.trim(),
        branchId: _selectedBranch,
        limit: 30,
      );
      if (!mounted || sequence != _requestSequence) return;
      // Scope checks here are a second defensive layer. The gateway and
      // LoanHub independently enforce the verified employee's privileges.
      final authorized = result.every((client) =>
          client.companyId == widget.staff.companyId &&
          (widget.staff.companyWide ||
              widget.staff.branchIds.contains(client.branchId)) &&
          (_selectedBranch == null || client.branchId == _selectedBranch));
      if (!authorized) {
        throw const FormatException('Client directory scope mismatch');
      }
      setState(() => _clients = result);
    } catch (_) {
      if (mounted && sequence == _requestSequence) {
        setState(() => _error =
            'Unable to retrieve authorized clients. Check your session and try again.');
      }
    } finally {
      if (mounted && sequence == _requestSequence) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  void dispose() {
    _requestSequence++;
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Find clients'),
      backgroundColor: BatlokoaDesign.navy, foregroundColor: Colors.white),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 760),
      child: ListView(padding: const EdgeInsets.all(20), children: [
        const BfsSectionTitle(eyebrow: 'CUSTOMER SEARCH',
          title: 'Authorized client directory',
          subtitle: 'Find and review clients using live LoanHub records.'),
        const SizedBox(height: 22),
        TextField(
          key: const Key('staff-client-search'),
          controller: _search,
          maxLength: 120,
          textInputAction: TextInputAction.search,
          onSubmitted: (_) => _load(),
          decoration: const InputDecoration(
            labelText: 'Search clients',
            hintText: 'Client name or account reference',
            prefixIcon: Icon(Icons.search),
            border: OutlineInputBorder(),
          ),
        ),
        if (widget.staff.companyWide && widget.staff.branchIds.isNotEmpty)
          DropdownButtonFormField<String>(
            key: const Key('staff-client-branch'),
            value: _selectedBranch,
            decoration: const InputDecoration(labelText: 'Branch'),
            items: [
              const DropdownMenuItem<String>(
                  value: null, child: Text('All authorized branches')),
              for (final branch in widget.staff.branchIds)
                DropdownMenuItem(value: branch, child: Text(branch)),
            ],
            onChanged: _busy ? null : (branch) {
              setState(() => _selectedBranch = branch);
              _load();
            },
          ),
        const SizedBox(height: 8),
        FilledButton.icon(
          key: const Key('staff-client-search-button'),
          onPressed: _busy ? null : _load,
          icon: const Icon(Icons.search),
          label: const Text('Find clients'),
        ),
        const SizedBox(height: 16),
        if (_busy) const Center(child: CircularProgressIndicator(
          key: Key('staff-clients-loading'))),
        if (_error != null)
          Card(child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              const Icon(Icons.error_outline),
              Text(_error!, key: const Key('staff-clients-error')),
              TextButton(onPressed: _busy ? null : _load,
                  child: const Text('Retry')),
            ]),
          )),
        if (!_busy && _error == null && _clients.isEmpty)
          const Card(child: Padding(
            padding: EdgeInsets.all(20),
            child: Text('No clients found in your authorized directory.'),
          )),
        if (!_busy && _error == null)
          for (final client in _clients)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Material(
                key: Key('staff-client-${client.accountId}'),
                color: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(18),
                  side: const BorderSide(color: Color(0xFFE2E7EE))),
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: () => showDialog<void>(
                    context: context,
                    builder: (dialogContext) => AlertDialog(
                      title: Text(client.fullName),
                      content: Text(
                        'Account: ${client.accountReference}\n'
                        'Status: ${client.status}\n'
                        'Loan applications and registration writes are not enabled.'),
                      actions: [TextButton(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('Close'))])),
                  child: Padding(padding: const EdgeInsets.all(16),
                    child: Row(children: [
                      const CircleAvatar(radius: 25,
                        backgroundColor: Color(0xFFEAF1FF),
                        child: Icon(Icons.person_outline_rounded,
                          color: BatlokoaDesign.accent)),
                      const SizedBox(width: 13),
                      Expanded(child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(client.fullName, maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 15,
                              fontWeight: FontWeight.w800,
                              color: BatlokoaDesign.navy)),
                          const SizedBox(height: 5),
                          Text(client.accountReference, maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 12,
                              color: BatlokoaDesign.silver)),
                          const SizedBox(height: 9),
                          BfsPill(label: client.status),
                        ])),
                      const Icon(Icons.arrow_forward_ios_rounded,
                        size: 15, color: BatlokoaDesign.silver),
                    ])),
                ),
              ),
            ),
      ]),
    ))),
  );
}
