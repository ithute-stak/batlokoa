import 'dart:async';
import 'package:flutter/material.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';

/// Recipient-scoped notification history. Never persist employee data.
class StaffNotificationScreen extends StatefulWidget {
  final StaffNotificationGateway gateway;
  const StaffNotificationScreen({super.key, required this.gateway});

  @override
  State<StaffNotificationScreen> createState() => _StaffNotificationScreenState();
}

class _StaffNotificationScreenState extends State<StaffNotificationScreen>
    with WidgetsBindingObserver {
  final _events = <StaffAttendanceNotification>[];
  StaffNotificationCursor? _before;
  bool _busy = false, _failed = false, _foreground = true;
  int _generation = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final state = WidgetsBinding.instance.lifecycleState;
    _foreground = state == null || state == AppLifecycleState.resumed;
    if (_foreground) {
      unawaited(_load(reset: true));
      _startTimer();
    }
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted && _foreground && !_busy &&
          ModalRoute.of(context)?.isCurrent == true) {
        unawaited(_load(reset: true));
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _generation++;
    _timer?.cancel();
    setState(() {
      _events.clear();
      _before = null;
      _busy = false;
      _failed = false;
    });
    if (_foreground) {
      _startTimer();
      if (ModalRoute.of(context)?.isCurrent == true) {
        unawaited(_load(reset: true));
      }
    }
  }

  @override
  void dispose() {
    _generation++;
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _load({bool reset = false}) async {
    if (_busy || !_foreground) return;
    final generation = _generation;
    final cursor = reset ? null : _before;
    setState(() {
      _busy = true;
      _failed = false;
    });
    try {
      final page = await widget.gateway.attendanceNotifications(before: cursor, limit: 50);
      if (!mounted || generation != _generation || !_foreground) return;
      setState(() {
        if (reset) _events.clear();
        final known = _events.map((event) => event.key).toSet();
        _events.addAll(page.notifications.where((event) => known.add(event.key)));
        _before = page.nextBefore;
      });
    } catch (_) {
      if (mounted && generation == _generation) {
        setState(() {
          _events.clear();
          _before = null;
          _failed = true;
        });
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  String _title(String kind) {
    switch (kind) {
      case 'morning_reminder': return 'Morning clock-in reminder';
      case 'reported_outside_perimeter': return 'Reported outside office perimeter';
      case 'reported_inside_perimeter': return 'Reported return to office';
      case 'reported_login_outside': return 'Reported login outside office';
      case 'staff_logged_out': return 'Employee signed out';
      default: return 'Attendance notification';
    }
  }

  String _time(DateTime value) {
    final local = value.toUtc().add(const Duration(hours: 2)).toIso8601String();
    return '${local.substring(0, 10)} ${local.substring(11, 19)} (Lesotho)';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Attendance notifications'), actions: [
      IconButton(tooltip: 'Refresh notifications', icon: const Icon(Icons.refresh),
        onPressed: _busy || !_foreground ? null : () => _load(reset: true)),
    ]),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 760),
      child: ListView(padding: BfsResponsive.pagePadding(context), children: [
        const Text('Attendance inbox',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        const Text('Location alerts reflect device-reported GPS, not independent proof of presence. Notifications refresh while this screen is open.'),
        const SizedBox(height: 12),
        Text(_failed ? 'Refresh to retry.' :
          'Newest events first. Automatic refresh returns to the latest page every 30 seconds while active.'),
        if (_busy) const LinearProgressIndicator(),
        if (_failed) const Text('Notifications unavailable or access denied.')
        else if (!_busy && _events.isEmpty) const Text('No current notifications.'),
        for (final event in _events.where((e) =>
            e.expiresAt == null || e.expiresAt!.isAfter(DateTime.now())))
          Card(child: ListTile(
            leading: Icon(event.eventType == 'morning_reminder'
                ? Icons.alarm : Icons.notifications_outlined),
            title: Text(_title(event.eventType)),
            subtitle: Text(event.eventType == 'morning_reminder'
                ? 'Please clock in for your scheduled workday.\n'+_time(event.observedAt)
                : 'Employee ID: '+event.employeeId+'\n'+_time(event.observedAt)),
          )),
        if (_before != null && !_failed)
          OutlinedButton(onPressed: _busy ? null : () => _load(),
            child: const Text('Load older notifications')),
      ]),
    ))),
  );
}
