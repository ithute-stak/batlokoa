import 'package:flutter/material.dart';

import 'bfs_responsive.dart';
import 'staff_gateway.dart';
import 'staff_location_capture.dart';

class OwnerBranchLocationScreen extends StatefulWidget {
  final StaffSession staff;
  final OwnerStaffManagementGateway directory;
  final StaffBranchLocationGateway gateway;
  final Future<StaffLocationCapture> Function() capture;

  const OwnerBranchLocationScreen({
    super.key,
    required this.staff,
    required this.directory,
    required this.gateway,
    this.capture = captureStaffLocation,
  });

  @override
  State<OwnerBranchLocationScreen> createState() =>
      _OwnerBranchLocationScreenState();
}

class _OwnerBranchLocationScreenState extends State<OwnerBranchLocationScreen> {
  final Map<String, String> _branches = {};
  String? _branch;
  StaffLocationCapture? _location;
  String? _message;
  bool _busy = true;
  bool _confirmed = false;

  bool get _owner =>
      widget.staff.role == 'COMPANY_OWNER' && widget.staff.companyWide;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!_owner) {
      setState(() { _busy = false; });
      return;
    }
    try {
      final rows = await widget.directory.ownerBranches();
      final branches = <String, String>{};
      for (final row in rows) {
        final id = row['id'];
        final name = row['name'];
        if (id is! String || name is! String || name.trim().isEmpty ||
            branches.containsKey(id) ||
            !RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$').hasMatch(id)) {
          throw const FormatException('Invalid branch directory');
        }
        branches[id] = name;
      }
      if (!mounted) return;
      setState(() {
        _branches.addAll(branches);
        _busy = false;
        if (branches.isEmpty) _message = 'No authorized branches available.';
      });
    } catch (_) {
      if (mounted) setState(() {
        _busy = false;
        _message = 'Branch directory unavailable. Reopen this page to retry.';
      });
    }
  }

  Future<void> _capture() async {
    if (!_owner || _busy || _branch == null) return;
    setState(() {
      _busy = true;
      _location = null;
      _confirmed = false;
      _message = null;
    });
    try {
      final reading = await widget.capture();
      if (!reading.isUsableAt(DateTime.now())) {
        throw StateError('Unusable location');
      }
      if (mounted) setState(() { _location = reading; });
    } catch (_) {
      if (mounted) setState(() {
        _message = 'Location unavailable or inaccurate. Enable precise location and retry at the branch.';
      });
    } finally {
      if (mounted) setState(() { _busy = false; });
    }
  }

  Future<void> _save() async {
    final branch = _branch;
    final location = _location;
    if (!_owner || _busy || !_confirmed || branch == null || location == null) return;
    if (!location.isUsableAt(DateTime.now())) {
      setState(() {
        _location = null;
        _confirmed = false;
        _message = 'Location expired. Capture your current location again.';
      });
      return;
    }
    setState(() { _busy = true; _message = null; });
    try {
      final revision = await widget.gateway.registerBranchLocation(branch, location);
      if (mounted) setState(() {
        _message = 'Branch location registered. Revision $revision.';
      });
    } catch (_) {
      if (mounted) setState(() {
        _message = 'Registration was not confirmed. Check with management before retrying.';
      });
    } finally {
      if (mounted) setState(() {
        _busy = false;
        _confirmed = false;
        _location = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Branch locations')),
      body: SafeArea(child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: BfsResponsive.pagePadding(context),
          children: [
            if (!_owner)
              const Text('Verified company owner access is required.')
            else ...[
              const Text('Register office location',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              const Text('Stand at the assigned branch. Capture your current device location. Manual coordinate entry is not available.'),
              const SizedBox(height: 20),
              InputDecorator(
                decoration: const InputDecoration(labelText: 'Branch'),
                child: DropdownButtonHideUnderline(child: DropdownButton<String>(
                  isExpanded: true,
                  value: _branch,
                  hint: const Text('Select branch'),
                  items: _branches.entries.map((entry) => DropdownMenuItem(
                    value: entry.key,
                    child: Text(entry.value, overflow: TextOverflow.ellipsis),
                  )).toList(),
                  onChanged: _busy ? null : (value) => setState(() {
                    _branch = value;
                    _location = null;
                    _confirmed = false;
                    _message = null;
                  }),
                )),
              ),
              const SizedBox(height: 16),
              const Text('Authorized radius: 10 metres'),
              const Text('Required location accuracy: 5 metres or better'),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: _busy || _branch == null ? null : _capture,
                icon: const Icon(Icons.my_location),
                label: const Text('Capture current location'),
              ),
              if (_location != null) ...[
                const SizedBox(height: 16),
                Text('Latitude: ${_location!.latitude.toStringAsFixed(7)}'),
                Text('Longitude: ${_location!.longitude.toStringAsFixed(7)}'),
                Text('Reported accuracy: ${_location!.accuracyM.toStringAsFixed(1)} m'),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('I confirm I am physically at this branch.'),
                  value: _confirmed,
                  onChanged: _busy ? null : (value) =>
                      setState(() { _confirmed = value == true; }),
                ),
                FilledButton(
                  onPressed: _busy || !_confirmed ? null : _save,
                  child: const Text('Register branch location'),
                ),
              ],
              if (_busy) const LinearProgressIndicator(),
              if (_message != null) Padding(
                padding: const EdgeInsets.only(top: 16),
                child: Semantics(liveRegion: true, child: Text(_message!)),
              ),
              const SizedBox(height: 16),
              const Text('Device location is an estimate, not proof of physical presence. The server independently checks registration authorization.'),
            ],
          ],
        ),
      ))),
    );
  }
}
