import 'package:flutter/material.dart';
import 'bfs_responsive.dart';
import 'staff_gateway.dart';

/// Owner schedule management. The API independently authorizes every write.
class OwnerWorkRosterScreen extends StatefulWidget {
  final OwnerWorkRosterGateway roster;
  final OwnerRosterEmployeeGateway directory;
  final OwnerWorkShiftGateway? shifts;
  const OwnerWorkRosterScreen({super.key, required this.roster, required this.directory, this.shifts});

  @override
  State<OwnerWorkRosterScreen> createState() => _OwnerWorkRosterScreenState();
}

class _OwnerWorkRosterScreenState extends State<OwnerWorkRosterScreen>
    with WidgetsBindingObserver {
  static DateTime _today() {
    final local = DateTime.now().toUtc().add(const Duration(hours: 2));
    return DateTime(local.year, local.month, local.day);
  }

  DateTime _day = _today();
  List<OwnerRosterEmployee> _employees = [];
  Map<String, bool> _schedule = {};
  Map<String, OwnerWorkShift> _shifts = {};
  bool _shiftFailed = false;
  bool _busy = false, _failed = false, _foreground = true;
  int _generation = 0;
  String? _notice;

  String get _date => _day.toIso8601String().substring(0, 10);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    _foreground = lifecycle == null || lifecycle == AppLifecycleState.resumed;
    if (_foreground) _load();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!mounted) return;
    _foreground = state == AppLifecycleState.resumed;
    _generation++;
    setState(() {
      _employees = [];
      _schedule = {};
      _shifts = {};
      _shiftFailed = false;
      _busy = false;
      _failed = false;
      _notice = null;
    });
    if (_foreground && ModalRoute.of(context)?.isCurrent == true) _load();
  }

  @override
  void dispose() {
    _generation++;
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _load({String? notice}) async {
    if (_busy || !_foreground) return;
    final generation = ++_generation;
    final date = _date;
    setState(() {
      _busy = true;
      _failed = false;
      _employees = [];
      _schedule = {};
      _shifts = {};
      _shiftFailed = false;
      _notice = null;
    });
    try {
      final employees = await widget.directory.rosterEmployees();
      if (!mounted || generation != _generation) return;
      final schedule = <String, bool>{};
      String? cursor;
      final seen = <String>{};
      // Do not interpret a partial roster as an unknown schedule.
      for (var pageIndex = 0; pageIndex < 100; pageIndex++) {
        final page = await widget.roster.workRoster(date, after: cursor, limit: 100);
        if (!mounted || generation != _generation) return;
        for (final row in page.rows) {
          schedule[row.employeeId] = row.scheduledToWork;
        }
        cursor = page.nextAfter;
        if (cursor == null) break;
        if (!seen.add(cursor) || pageIndex == 99) {
          throw StateError('Incomplete roster');
        }
      }
      final shifts = <String, OwnerWorkShift>{};
      var shiftFailed = false;
      final shiftGateway = widget.shifts;
      if (shiftGateway != null) {
        try {
          String? shiftCursor;
          final seenShifts = <String>{};
          for (var i = 0; i < 100; i++) {
            final page = await shiftGateway.workShifts(date, after: shiftCursor, limit: 100);
            if (!mounted || generation != _generation) return;
            for (final row in page.rows) {
              if (shifts.containsKey(row.employeeId)) throw StateError('Duplicate shift');
              shifts[row.employeeId] = row;
            }
            shiftCursor = page.nextAfter;
            if (shiftCursor == null) break;
            if (!seenShifts.add(shiftCursor) || i == 99) throw StateError('Incomplete shifts');
          }
        } catch (_) {
          shifts.clear();
          shiftFailed = true;
        }
      }
      if (!mounted || generation != _generation) return;
      setState(() {
        _shifts = shifts;
        _shiftFailed = shiftFailed;
        _employees = employees;
        _schedule = schedule;
        _notice = notice;
      });
    } catch (_) {
      if (mounted && generation == _generation) {
        setState(() {
          _employees = [];
          _schedule = {};
      _shifts = {};
      _shiftFailed = false;
          _failed = true;
        });
      }
    } finally {
      if (mounted && generation == _generation) setState(() => _busy = false);
    }
  }

  Future<void> _pickDay() async {
    if (_busy || !_foreground) return;
    final today = _today();
    final last = DateTime(today.year, today.month, today.day + 366);
    final initial = _day.isBefore(today) || _day.isAfter(last) ? today : _day;
    final generation = _generation;
    final selected = await showDatePicker(context: context, initialDate: initial,
        firstDate: today, lastDate: last);
    if (!mounted || selected == null || !_foreground || generation != _generation) return;
    setState(() => _day = selected);
    await _load();
  }

  Future<void> _assign(OwnerRosterEmployee employee, bool working) async {
    if (_busy || _failed || !_foreground || !_employees.contains(employee)) return;
    final generation = _generation;
    final date = _date;
    final confirmed = await showDialog<bool>(context: context, builder: (context) =>
      AlertDialog(title: const Text('Confirm working schedule'),
        content: Text('${employee.name ?? employee.employeeId}\n$date\n'
          '${working ? "Working day" : "Non-working day"}'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm')),
        ]));
    if (!mounted || confirmed != true || !_foreground || _busy ||
        generation != _generation || date != _date) return;
    setState(() { _busy = true; _notice = null; });
    String notice;
    try {
      await widget.roster.setWorkDay(employee.employeeId, date, scheduledToWork: working);
      notice = 'Schedule confirmed by server.';
    } catch (_) {
      notice = 'Update not confirmed. Check the refreshed schedule before retrying.';
    }
    if (!mounted || generation != _generation || !_foreground) return;
    setState(() => _busy = false);
    await _load(notice: notice);
  }

  String _shiftTime(DateTime value) {
    final local = value.toUtc().add(const Duration(hours: 2));
    return local.toIso8601String().substring(11, 16);
  }

  Future<void> _editShift(OwnerRosterEmployee employee) async {
    final gateway = widget.shifts;
    if (gateway == null || _busy || _failed || _shiftFailed || !_foreground ||
        _schedule[employee.employeeId] != true) return;
    final generation = _generation;
    final date = _date;
    final current = _shifts[employee.employeeId];
    final result = await showDialog<_ShiftDraft>(
      context: context,
      builder: (_) => _ShiftEditor(employee: employee, current: current),
    );
    if (!mounted || result == null || generation != _generation ||
        !_foreground || _busy || date != _date) return;
    final day = DateTime.parse(date);
    final start = DateTime.utc(day.year, day.month, day.day,
        result.start.hour - 2, result.start.minute);
    var end = DateTime.utc(day.year, day.month, day.day,
        result.end.hour - 2, result.end.minute);
    if (result.overnight) end = end.add(const Duration(days: 1));
    setState(() { _busy = true; _notice = null; });
    String notice;
    try {
      await gateway.setWorkShift(employee.employeeId, date,
          startsAt: start, endsAt: end, graceMinutes: result.grace);
      notice = 'Shift confirmed by server.';
    } catch (_) {
      notice = 'Shift update not confirmed. Check the refreshed shift before retrying.';
    }
    if (!mounted || generation != _generation || !_foreground) return;
    setState(() => _busy = false);
    await _load(notice: notice);
  }

  Widget _rosterSummary(BuildContext context) {
    final working = _employees.where((e) => _schedule[e.employeeId] == true).length;
    final nonWorking = _employees.where((e) => _schedule[e.employeeId] == false).length;
    final unknown = _employees.length - working - nonWorking;
    final theme = Theme.of(context);
    return LayoutBuilder(builder: (context, constraints) {
      final columns = constraints.maxWidth >= 680 &&
          BfsResponsive.textScale(context) <= 1.35 ? 4 :
          constraints.maxWidth >= 340 &&
          BfsResponsive.textScale(context) <= 1.35 ? 2 : 1;
      final width = (constraints.maxWidth - (columns - 1) * 12) / columns;
      Widget metric(String label, int count) => SizedBox(
        width: width,
        child: Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(label, style: theme.textTheme.bodyMedium),
              const SizedBox(height: 8),
              Text('$count', style: theme.textTheme.headlineMedium?.copyWith(
                  color: theme.colorScheme.primary, fontWeight: FontWeight.w700)),
            ]),
          ),
        ),
      );
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Schedule overview', style: theme.textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text('Planned schedules only, not actual attendance or absence.'),
        const SizedBox(height: 12),
        Wrap(spacing: 12, runSpacing: 12, children: [
          metric('Eligible employees', _employees.length),
          metric('Scheduled to work', working),
          metric('Non-working day', nonWorking),
          metric('Schedule unknown', unknown),
        ]),
      ]);
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Employee working schedules'), actions: [
      IconButton(tooltip: 'Refresh working schedules', icon: const Icon(Icons.refresh),
        onPressed: _busy || !_foreground ? null : () => _load()),
    ]),
    body: SafeArea(child: Center(child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1200),
      child: ListView(padding: BfsResponsive.pagePadding(context), children: [
        const Text('Daily work roster', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        const Text('Assign working or non-working days. Unknown schedules do not trigger morning reminders. Dates use Lesotho time.'),
        const SizedBox(height: 12),
        OutlinedButton.icon(onPressed: _busy || !_foreground ? null : _pickDay,
          icon: const Icon(Icons.calendar_today), label: Text(_date)),
        if (_busy) const LinearProgressIndicator(),
        if (_notice != null) Text(_notice!),
        if (_shiftFailed) const Text('Shift details unavailable. Refresh before editing.'),
        if (_failed) const Text('Working schedule unavailable or access denied. Refresh to retry.'),
        if (!_busy && !_failed && _employees.isEmpty) const Text('No eligible employees returned.'),
        if (!_busy && !_failed && _foreground && _employees.isNotEmpty) ...[
          const SizedBox(height: 16),
          _rosterSummary(context),
          const SizedBox(height: 24),
        ],
        for (final employee in _employees)
          Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(
            crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(employee.name ?? 'Unknown name (ID: ${employee.employeeId})',
                style: const TextStyle(fontWeight: FontWeight.w600)),
              Text(employee.role.replaceAll('_', ' ')),
              Text(_schedule[employee.employeeId] == true ? 'Working day' :
                _schedule[employee.employeeId] == false ? 'Non-working day' : 'Schedule unknown'),
              if (widget.shifts != null && _schedule[employee.employeeId] == true && !_shiftFailed)
                Text(_shifts[employee.employeeId] == null ? 'Shift times not configured' :
                  '${_shiftTime(_shifts[employee.employeeId]!.startsAt)} – ${_shiftTime(_shifts[employee.employeeId]!.endsAt)} · Grace: ${_shifts[employee.employeeId]!.graceMinutes} min'),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                OutlinedButton(onPressed: _busy || !_foreground ? null : () => _assign(employee, true),
                  child: const Text('Working')),
                OutlinedButton(onPressed: _busy || !_foreground ? null : () => _assign(employee, false),
                  child: const Text('Non-working')),
                if (widget.shifts != null && _schedule[employee.employeeId] == true)
                  OutlinedButton(onPressed: _busy || !_foreground || _shiftFailed ? null : () => _editShift(employee),
                    child: const Text('Configure shift')),
              ]),
            ],
          ))),
      ]),
    ))),
  );
}


class _ShiftDraft {
  final TimeOfDay start, end;
  final bool overnight;
  final int grace;
  const _ShiftDraft(this.start, this.end, this.overnight, this.grace);
}

class _ShiftEditor extends StatefulWidget {
  final OwnerRosterEmployee employee;
  final OwnerWorkShift? current;
  const _ShiftEditor({required this.employee, this.current});

  @override
  State<_ShiftEditor> createState() => _ShiftEditorState();
}

class _ShiftEditorState extends State<_ShiftEditor> {
  TimeOfDay? _start, _end;
  bool _overnight = false;
  int _grace = 0;

  @override
  void initState() {
    super.initState();
    final shift = widget.current;
    if (shift != null) {
      final start = shift.startsAt.toUtc().add(const Duration(hours: 2));
      final end = shift.endsAt.toUtc().add(const Duration(hours: 2));
      _start = TimeOfDay(hour: start.hour, minute: start.minute);
      _end = TimeOfDay(hour: end.hour, minute: end.minute);
      _overnight = start.day != end.day || start.month != end.month || start.year != end.year;
      _grace = shift.graceMinutes;
    }
  }

  int _minutes(TimeOfDay t) => t.hour * 60 + t.minute;
  bool get _valid {
    if (_start == null || _end == null) return false;
    final duration = _minutes(_end!) - _minutes(_start!) + (_overnight ? 1440 : 0);
    return duration > _grace && duration <= 1440;
  }

  Future<void> _pick(bool start) async {
    final value = await showTimePicker(context: context,
        initialTime: (start ? _start : _end) ?? const TimeOfDay(hour: 8, minute: 0));
    if (!mounted || value == null) return;
    setState(() { if (start) { _start = value; } else { _end = value; } });
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    scrollable: true,
    title: const Text('Configure working shift'),
    content: Column(mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(widget.employee.name ?? widget.employee.employeeId),
        const Text('All times are Lesotho time.'),
        OutlinedButton(onPressed: () => _pick(true),
          child: Text(_start == null ? 'Select starting time' : 'Start: ${_start!.format(context)}')),
        OutlinedButton(onPressed: () => _pick(false),
          child: Text(_end == null ? 'Select finishing time' : 'End: ${_end!.format(context)}')),
        CheckboxListTile(contentPadding: EdgeInsets.zero, title: const Text('Ends next day'),
          value: _overnight, onChanged: (value) => setState(() => _overnight = value ?? false)),
        Text('Grace period: $_grace minutes'),
        Slider(value: _grace.toDouble(), min: 0, max: 120, divisions: 120,
          label: '$_grace min', onChanged: (value) => setState(() => _grace = value.round())),
        if (!_valid) const Text('Select a valid shift of at most 24 hours, longer than its grace period.'),
      ]),
    actions: [
      TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(onPressed: !_valid ? null : () => Navigator.pop(context,
        _ShiftDraft(_start!, _end!, _overnight, _grace)), child: const Text('Save shift')),
    ],
  );
}
