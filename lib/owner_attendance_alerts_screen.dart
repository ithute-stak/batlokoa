import 'package:flutter/material.dart';

import 'bfs_responsive.dart';
import 'staff_gateway.dart';

/// Read-only, owner-authorized view. No location samples or local persistence.
class OwnerAttendanceAlertsScreen extends StatefulWidget {
  final OwnerAttendanceInboxGateway gateway;
  const OwnerAttendanceAlertsScreen({super.key, required this.gateway});

  @override
  State<OwnerAttendanceAlertsScreen> createState() => _OwnerAttendanceAlertsScreenState();
}

class _OwnerAttendanceAlertsScreenState extends State<OwnerAttendanceAlertsScreen> {
  static const _pageSize = 50;
  final List<OwnerAttendanceAlert> _alerts = [];
  int _after = 0;
  bool _more = false;
  bool _busy = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load(reset: true);
  }

  Future<void> _load({bool reset = false}) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _failed = false;
      if (reset) {
        _alerts.clear();
        _after = 0;
        _more = false;
      }
    });
    try {
      final page = await widget.gateway.attendanceAlerts(after: _after, limit: _pageSize);
      if (!mounted) return;
      setState(() {
        _alerts.addAll(page.alerts);
        _after = page.nextAfter;
        _more = page.hasMore;
      });
    } catch (_) {
      if (mounted) setState(() {
        // Do not leave previously authorized data visible after access failure.
        _alerts.clear();
        _after = 0;
        _more = false;
        _failed = true;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _time(DateTime value) {
    final local = value.toUtc().add(const Duration(hours: 2)).toIso8601String();
    return '${local.substring(0, 10)} ${local.substring(11, 19)} (Lesotho)';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Attendance alerts'), actions: [
        IconButton(tooltip: 'Refresh alerts', icon: const Icon(Icons.refresh),
          onPressed: _busy ? null : () => _load(reset: true)),
      ]),
      body: SafeArea(child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: ListView(padding: BfsResponsive.pagePadding(context), children: [
          const Text('Confirmed perimeter observations',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          const Text('These events reflect device-reported location, not independent '
              'proof of physical presence. Missing GPS or network access is not a departure.'),
          const SizedBox(height: 16),
          if (_busy) const LinearProgressIndicator(),
          if (_failed)
            const Text('Attendance alerts unavailable or access denied.')
          else if (!_busy && _alerts.isEmpty)
            const Text('No confirmed perimeter alerts recorded.'),
          for (final alert in _alerts.reversed)
            Card(child: ListTile(
              leading: Icon(alert.eventType == 'reported_outside_perimeter'
                  ? Icons.warning_amber_rounded : Icons.check_circle_outline),
              title: Text(alert.eventType == 'reported_outside_perimeter'
                  ? 'Reported outside office perimeter' : 'Reported return inside perimeter'),
              subtitle: Text('Employee ID: ${alert.employeeId}\n'
                  'Branch ID: ${alert.branchId}\n'
                  'Session: ${alert.sessionId}\n${_time(alert.observedAt)}'),
            )),
          if (_more && !_failed)
            OutlinedButton(onPressed: _busy ? null : () => _load(),
              child: const Text('Load more alerts')),
        ]),
      ))),
    );
  }
}
