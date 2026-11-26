import 'dart:async';
import 'package:flutter/material.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';

/// Owner-only server-authorized access history. Never persist employee data.
class OwnerAccessEventsScreen extends StatefulWidget {
  final OwnerAccessInboxGateway gateway;
  const OwnerAccessEventsScreen({super.key, required this.gateway});

  @override
  State<OwnerAccessEventsScreen> createState() => _OwnerAccessEventsScreenState();
}

class _OwnerAccessEventsScreenState extends State<OwnerAccessEventsScreen>
    with WidgetsBindingObserver {
  final _events = <OwnerAccessEvent>[];
  OwnerAccessCursor? _before;
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
      if (mounted && _foreground && !_busy && !_failed &&
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
      final page = await widget.gateway.accessEvents(before: cursor, limit: 50);
      if (!mounted || generation != _generation || !_foreground) return;
      setState(() {
        if (reset) _events.clear();
        final known = _events.map((event) => event.id).toSet();
        _events.addAll(page.events.where((event) => known.add(event.id)));
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

  String _time(DateTime value) {
    final local = value.toUtc().add(const Duration(hours: 2)).toIso8601String();
    return '${local.substring(0, 10)} ${local.substring(11, 19)} (Lesotho)';
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Employee access events'), actions: [
      IconButton(tooltip: 'Refresh access events', icon: const Icon(Icons.refresh),
        onPressed: _busy || !_foreground ? null : () => _load(reset: true)),
    ]),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 760),
      child: ListView(padding: BfsResponsive.pagePadding(context), children: [
        const Text('Login and logout history',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        const Text('Outside-office events reflect device-reported GPS, not independent proof of presence. Missing GPS is not an outside-office event. Signing out is not the same as clocking out.'),
        const SizedBox(height: 12),
        Text(_failed ? 'Refresh to retry.' :
          'Newest events first. Automatic refresh returns to the latest page every 30 seconds while active.'),
        if (_busy) const LinearProgressIndicator(),
        if (_failed) const Text('Access events unavailable or access denied.')
        else if (!_busy && _events.isEmpty) const Text('No access events recorded.'),
        for (final event in _events)
          Card(child: ListTile(
            leading: Icon(event.eventType == 'reported_login_outside'
              ? Icons.warning_amber_rounded : Icons.logout),
            title: Text(event.eventType == 'reported_login_outside'
              ? 'Reported login outside office' : 'Employee signed out'),
            subtitle: Text('Employee: ${event.employeeName ?? "Unknown name (ID: ${event.employeeId})"}\n'
              'Branch: ${event.branchName ?? (event.branchId == null ? "Not determined" : "Unknown name (ID: ${event.branchId})")}\n'
              '${_time(event.observedAt)}'),
          )),
        if (_before != null && !_failed)
          OutlinedButton(onPressed: _busy ? null : () => _load(),
            child: const Text('Load older events')),
      ]),
    ))),
  );
}
