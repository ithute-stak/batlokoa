import 'package:flutter/material.dart';

import 'activity_details.dart';

/// Searchable sample activity, deliberately detached from real payments.
class ActivityHistoryPage extends StatefulWidget {
  const ActivityHistoryPage({super.key});

  @override
  State<ActivityHistoryPage> createState() => _ActivityHistoryPageState();
}

class _ActivityHistoryPageState extends State<ActivityHistoryPage> {
  String query = '';
  String filter = 'All';
  static const filters = ['All', 'Money in', 'Money out'];

  bool matches(DemoActivity activity) {
    final isIncoming = activity.amount.startsWith('+');
    final matchesDirection = filter == 'All' ||
        (filter == 'Money in' && isIncoming) ||
        (filter == 'Money out' && !isIncoming);
    final term = query.trim().toLowerCase();
    final matchesSearch = term.isEmpty ||
        activity.title.toLowerCase().contains(term) ||
        activity.source.toLowerCase().contains(term) ||
        activity.id.toLowerCase().contains(term);
    return matchesDirection && matchesSearch;
  }

  @override
  Widget build(BuildContext context) {
    final items = demoActivities.where(matches).toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Transaction history')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 760),
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const Text(
                  'Sample transactions — not financial records',
                  style: TextStyle(color: Colors.black54),
                ),
                const SizedBox(height: 16),
                TextField(
                  key: const Key('activity-search'),
                  textInputAction: TextInputAction.search,
                  decoration: const InputDecoration(
                    labelText: 'Search activity',
                    hintText: 'Service or reference',
                    prefixIcon: Icon(Icons.search),
                  ),
                  onChanged: (value) => setState(() => query = value),
                ),
                const SizedBox(height: 12),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      for (final option in filters)
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: ChoiceChip(
                            label: Text(option),
                            selected: filter == option,
                            onSelected: (_) => setState(() => filter = option),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                if (items.isEmpty)
                  Card(
                    color: Colors.white,
                    child: Padding(
                      padding: const EdgeInsets.all(30),
                      child: Column(
                        children: [
                          const Icon(Icons.search_off_outlined, size: 40),
                          const SizedBox(height: 12),
                          const Text('No matching transactions'),
                          const SizedBox(height: 8),
                          const Text(
                            'Try a different search or clear the filters.',
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          TextButton(
                            onPressed: () => setState(() {
                              query = '';
                              filter = 'All';
                            }),
                            child: const Text('Show all activity'),
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  Card(
                    color: Colors.white,
                    child: Column(
                      children: [
                        for (var i = 0; i < items.length; i++) ...[
                          if (i > 0) const Divider(height: 1),
                          ListTile(
                            key: ValueKey(items[i].id),
                            leading: CircleAvatar(
                              backgroundColor: const Color(0xFFF0F7F4),
                              child: Icon(items[i].icon, color: const Color(0xFF113F3C)),
                            ),
                            title: Text(items[i].title),
                            subtitle: Text(items[i].date),
                            trailing: Text(items[i].amount,
                                style: const TextStyle(fontWeight: FontWeight.bold)),
                            onTap: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => DemoActivityPage(activity: items[i]),
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
