import 'package:flutter/material.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';

class OwnerAttendanceReportScreen extends StatefulWidget {
  final OwnerAttendanceReportGateway gateway;
  const OwnerAttendanceReportScreen({super.key, required this.gateway});

  @override
  State<OwnerAttendanceReportScreen> createState() => _OwnerAttendanceReportScreenState();
}

class _OwnerAttendanceReportScreenState extends State<OwnerAttendanceReportScreen>
    with WidgetsBindingObserver {
  static DateTime _today() {
    final now = DateTime.now().toUtc().add(const Duration(hours: 2));
    return DateTime(now.year, now.month, now.day);
  }
  DateTime _day = _today();
  List<OwnerDailyAttendanceBranch> _rows = [];
  bool _busy = false, _failed = false, _foreground = true;
  int _generation = 0;
  String get _date => _day.toIso8601String().substring(0, 10);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final state = WidgetsBinding.instance.lifecycleState;
    _foreground = state == null || state == AppLifecycleState.resumed;
    if (_foreground) _load();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    _generation++;
    setState(() {
      _foreground = state == AppLifecycleState.resumed;
      _rows = [];
      _busy = false;
      _failed = false;
    });
    if (_foreground) _load();
  }

  @override
  void dispose() {
    _generation++;
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _load() async {
    if (_busy || !_foreground) return;
    final generation = ++_generation;
    setState(() { _busy = true; _failed = false; _rows = []; });
    try {
      final rows = await widget.gateway.dailyAttendanceSummary(_date);
      if (!mounted || generation != _generation) return;
      setState(() => _rows = rows);
    } catch (_) {
      if (mounted && generation == _generation) {
        setState(() { _failed = true; _rows = []; });
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _pickDate() async {
    final generation = _generation;
    final selected = await showDatePicker(context: context, initialDate: _day,
        firstDate: DateTime(2020), lastDate: _today());
    if (!mounted || selected == null || !_foreground || generation != _generation) return;
    setState(() => _day = selected);
    await _load();
  }

  String _duration(int seconds) => '${seconds ~/ 3600}h ${(seconds ~/ 60) % 60}m';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final seconds = _rows.fold<int>(0, (sum, row) => sum + row.recordedSeconds);
    return Scaffold(
      appBar: AppBar(title: const Text('Attendance reports'), actions: [
        IconButton(tooltip: 'Refresh report', onPressed: _busy || !_foreground ? null : _load,
            icon: const Icon(Icons.refresh)),
      ]),
      body: SafeArea(child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1200),
        child: ListView(padding: BfsResponsive.pagePadding(context), children: [
          Text('Daily attendance overview', style: theme.textTheme.headlineSmall),
          const Text('Lesotho calendar day. Completed session duration only; not payroll hours.'),
          const SizedBox(height: 16),
          OutlinedButton.icon(onPressed: _busy || !_foreground ? null : _pickDate,
              icon: const Icon(Icons.calendar_today), label: Text(_date)),
          if (_busy) const LinearProgressIndicator(),
          if (_failed) const Text('Attendance report unavailable or access denied. Refresh to retry.'),
          if (!_busy && !_failed && _foreground) ...[
            const SizedBox(height: 16),
            Text('Total recorded duration: ${_duration(seconds)}',
                style: theme.textTheme.titleLarge?.copyWith(color: theme.colorScheme.primary)),
            const SizedBox(height: 12),
            if (_rows.isEmpty) const Text('No attendance records for this date.'),
            for (final row in _rows)
              Card(child: Padding(padding: const EdgeInsets.all(16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Branch: ${row.branchId}', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text('Employees with records: ${row.employeesWithRecords}'),
                  Text('Open sessions: ${row.openSessions}'),
                  Text('Completed sessions: ${row.closedSessions}'),
                  Text('Recorded duration: ${_duration(row.recordedSeconds)}'),
                ]))),
          ],
        ]),
      ))),
    );
  }
}
