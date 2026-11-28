import 'package:flutter/material.dart';

import 'bfs_responsive.dart';
import 'staff_gateway.dart';
import 'staff_location_capture.dart';

/// Explicit attendance actions only; no background location collection.
class StaffAttendanceScreen extends StatefulWidget {
  final StaffSession staff;
  final StaffAttendanceGateway gateway;
  final Map<String, String> branches;
  final Future<StaffLocationCapture> Function() capture;

  const StaffAttendanceScreen({
    super.key,
    required this.staff,
    required this.gateway,
    required this.branches,
    this.capture = captureStaffLocation,
  });

  @override
  State<StaffAttendanceScreen> createState() => _StaffAttendanceScreenState();
}

class _StaffAttendanceScreenState extends State<StaffAttendanceScreen> {
  StaffAttendanceSession? _open;
  List<StaffAttendanceSession> _history = [];
  String? _branch;
  String? _message;
  bool _busy = true;
  bool _verified = false;
  bool _historyAvailable = false;

  Map<String, String> get _authorized => Map.fromEntries(
      widget.branches.entries.where((entry) =>
          widget.staff.branchIds.contains(entry.key) ||
          (widget.staff.companyWide &&
              ['COMPANY_OWNER', 'COMPANY_ADMIN'].contains(widget.staff.role))));

  @override
  void initState() {
    super.initState();
    if (_authorized.length == 1) _branch = _authorized.keys.first;
    _refresh();
  }

  Future<void> _refresh() async {
    try {
      final status = await widget.gateway.attendanceStatus();
      if (!mounted) return;
      setState(() {
        _open = status;
        _verified = true;
        _historyAvailable = false;
        _history = [];
      });
      final rows = await widget.gateway.attendanceHistory();
      if (!mounted) return;
      setState(() {
        _history = rows;
        _historyAvailable = true;
      });
    } catch (_) {
      if (mounted) setState(() {
        _message ??= 'Attendance information could not be refreshed.';
      });
    } finally {
      if (mounted) setState(() { _busy = false; });
    }
  }

  Future<void> _reload() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _verified = false;
      _message = null;
    });
    await _refresh();
  }

  Future<void> _record() async {
    final clockIn = _open == null;
    final branch = clockIn ? _branch : _open?.branchId;
    if (_busy || !_verified || branch == null ||
        !_authorized.containsKey(branch)) return;
    setState(() { _busy = true; _message = null; });
    try {
      final reading = await widget.capture();
      if (!mounted) return;
      if (!reading.isUsableAt(DateTime.now())) {
        setState(() {
          _message = 'Location unavailable or inaccurate. Enable precise location and try again.';
          _busy = false;
        });
        return;
      }
      // A failed or interrupted response may still have committed; do not
      // permit another write until the authoritative status is refreshed.
      setState(() { _verified = false; });
      await widget.gateway.recordAttendance(branch, reading, clockIn: clockIn);
      if (!mounted) return;
      setState(() {
        _message = clockIn ? 'Clock-in recorded.' : 'Clock-out recorded.';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _verified = false;
        _message = error is StateError &&
                error.message == 'You are outside the authorized office perimeter.'
            ? 'You are outside the authorized office perimeter.'
            : 'Attendance not confirmed. Check your current status before retrying.';
      });
    }
    if (mounted) await _refresh();
  }

  String _time(DateTime value) {
    final local = value.toUtc().add(const Duration(hours: 2));
    final date = local.toIso8601String();
    return '${date.substring(0, 10)} ${date.substring(11, 16)} (Lesotho)';
  }

  @override
  Widget build(BuildContext context) {
    final open = _open;
    final selected = open?.branchId ?? _branch;
    return Scaffold(
      appBar: AppBar(title: const Text('My attendance'), actions: [
        IconButton(onPressed: _busy ? null : _reload,
            tooltip: 'Refresh attendance', icon: const Icon(Icons.refresh)),
      ]),
      body: SafeArea(child: LayoutBuilder(builder: (context, constraints) {
        final wide = constraints.maxWidth >= 1000 &&
            BfsResponsive.textScale(context) <= 1.35;
        final theme = Theme.of(context);
        final colors = theme.colorScheme;
        final clocking = Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('Current attendance', style: theme.textTheme.titleMedium),
              const SizedBox(height: 12),
              Text(!_verified ? 'Attendance status unverified'
                  : open == null ? 'Clocked out' : 'Clocked in',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    color: _verified && open != null ? colors.primary : null,
                    fontWeight: FontWeight.w700)),
              if (open != null && _verified)
                Text('Clocked in at ${_time(open.clockedInAt)}'),
              const SizedBox(height: 20),
              if (open == null)
                DropdownButtonFormField<String>(
                  initialValue: _branch,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Assigned branch'),
                  items: _authorized.entries.map((entry) => DropdownMenuItem(
                    value: entry.key, child: Text(entry.value,
                        overflow: TextOverflow.ellipsis),
                  )).toList(),
                  onChanged: _busy || !_verified ? null : (value) =>
                      setState(() { _branch = value; }),
                )
              else
                Text('Branch: ${_authorized[open.branchId] ?? "Previous assigned branch"}'),
              const SizedBox(height: 16),
              FilledButton.icon(
                key: const Key('staff-attendance-record'),
                style: FilledButton.styleFrom(
                    minimumSize: const Size(0, 52),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12)),
                onPressed: _busy || !_verified || selected == null ||
                    !_authorized.containsKey(selected) ? null : _record,
                icon: const Icon(Icons.my_location),
                label: Text(open == null ? 'Clock In' : 'Clock Out'),
              ),
              if (_busy) const Padding(padding: EdgeInsets.only(top: 12),
                  child: LinearProgressIndicator()),
              if (_message != null)
                Padding(padding: const EdgeInsets.only(top: 12),
                    child: Semantics(liveRegion: true, child: Text(_message!))),
            ]),
          ),
        );
        final location = Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(Icons.location_on_outlined, color: colors.primary),
              const SizedBox(height: 8),
              Text('Office location', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              const Text('You must be within the registered 10-metre office perimeter. '
                  'Location is requested only when you press a clocking button.'),
            ]),
          ),
        );
        final history = Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text('Recent attendance', style: theme.textTheme.titleLarge),
              const SizedBox(height: 12),
              if (!_historyAvailable) const Text('Attendance history unavailable.')
              else if (_history.isEmpty) const Text('No attendance sessions recorded.')
              else for (final session in _history)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(_authorized[session.branchId] ?? 'Previous assigned branch',
                        style: theme.textTheme.titleSmall),
                    Text('In: ${_time(session.clockedInAt)}\n'
                        'Out: ${session.clockedOutAt == null ? "Open" : _time(session.clockedOutAt!)}'),
                    const Divider(),
                  ]),
                ),
            ]),
          ),
        );
        return Center(child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: wide ? 1440 : 680),
          child: ListView(padding: BfsResponsive.pagePadding(context), children: [
            if (wide)
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: Column(children: [
                  clocking, const SizedBox(height: 16), location,
                ])),
                const SizedBox(width: 20),
                Expanded(child: history),
              ])
            else ...[
              clocking, const SizedBox(height: 16), location,
              const SizedBox(height: 16), history,
            ],
          ]),
        ));
      })),
    );
  }
}
