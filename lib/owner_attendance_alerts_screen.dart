import 'dart:async';

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

class _OwnerAttendanceAlertsScreenState extends State<OwnerAttendanceAlertsScreen> with WidgetsBindingObserver {
  static const _pageSize = 50;
  final List<OwnerAttendanceAlert> _alerts = [];
  int _after = 0;
  bool _more = false;
  bool _busy = false;
  bool _failed = false;
  Timer? _refreshTimer;
  bool _foreground = true;
  int _generation = 0;
  static const _maxPollPages = 10;

  @override
  void initState() {
    super.initState();
    final state = WidgetsBinding.instance.lifecycleState;
    _foreground = state == null || state == AppLifecycleState.resumed;
    WidgetsBinding.instance.addObserver(this);
    if (_foreground) {
      _load(reset: true);
      _startTimer();
    }
  }

  void _startTimer() {
    _refreshTimer?.cancel();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted && _foreground && !_busy && !_failed &&
          ModalRoute.of(context)?.isCurrent == true) {
        unawaited(_poll());
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    _foreground = state == AppLifecycleState.resumed;
    if (!_foreground) {
      _refreshTimer?.cancel();
      _generation++;
      setState(() {
        _alerts.clear();
        _after = 0;
        _more = false;
        _busy = false;
      });
    } else {
      _startTimer();
      if (ModalRoute.of(context)?.isCurrent == true) {
        unawaited(_load(reset: true));
      }
    }
  }

  @override
  void dispose() {
    _generation++;
    _refreshTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _poll() async {
    if (_busy || !_foreground) return;
    // Re-scan the displayed prefix rather than relying on a high-water mark:
    // database identity values can be allocated before a transaction commits.
    // Keep polling bounded; larger histories require a manual refresh.
    final pages = (_alerts.length ~/ _pageSize) + 1;
    if (pages > _maxPollPages) return;
    final generation = _generation;
    setState(() => _busy = true);
    try {
      final fresh = <int, OwnerAttendanceAlert>{};
      var cursor = 0;
      var more = false;
      for (var i = 0; i < pages; i++) {
        final page = await widget.gateway.attendanceAlerts(after: cursor, limit: _pageSize);
        if (!mounted || generation != _generation || !_foreground) return;
        for (final alert in page.alerts) {
          fresh[alert.id] = alert;
        }
        cursor = page.nextAfter;
        more = page.hasMore;
        if (!more) break;
      }
      setState(() {
        _alerts..clear()..addAll(fresh.values);
        _after = cursor;
        _more = more;
      });
    } catch (_) {
      if (mounted && generation == _generation) setState(() {
        _alerts.clear();
        _after = 0;
        _more = false;
        _failed = true;
      });
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _load({bool reset = false}) async {
    if (_busy || !_foreground) return;
    final generation = _generation;
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
      if (!mounted || generation != _generation || !_foreground) return;
      setState(() {
        final known = _alerts.map((alert) => alert.id).toSet();
        _alerts.addAll(page.alerts.where((alert) => known.add(alert.id)));
        _after = page.nextAfter;
        _more = page.hasMore;
      });
    } catch (_) {
      if (mounted && generation == _generation) setState(() {
        // Do not leave previously authorized data visible after access failure.
        _alerts.clear();
        _after = 0;
        _more = false;
        _failed = true;
      });
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
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
          Text(_failed ? 'Automatic refresh paused. Refresh to retry.'
              : _alerts.length >= _maxPollPages * _pageSize
                  ? 'Large history: use manual refresh.'
                  : 'Automatic refresh every 30 seconds while this screen is active.'),
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
              subtitle: Text('Employee: ${alert.employeeName ?? "Unknown name (ID: ${alert.employeeId})"}\n'
                  'Branch: ${alert.branchName ?? "Unknown name (ID: ${alert.branchId})"}\n'
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
