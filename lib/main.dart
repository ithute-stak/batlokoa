import 'package:flutter/material.dart';
import 'customer_flows.dart';
import 'payment_review.dart';
import 'activity_history.dart';
import 'input_validators.dart';

void main() => runApp(const BatlokoaApp());
const teal=Color(0xFF113F3C), mint=Color(0xFF16A48B), bg=Color(0xFFF4F8F7);
class BatlokoaApp extends StatelessWidget {
  const BatlokoaApp({super.key});
  @override Widget build(BuildContext context)=>MaterialApp(
    debugShowCheckedModeBanner:false,title:'Batlokoa Finance',
    theme:ThemeData(useMaterial3:true,scaffoldBackgroundColor:bg,
      colorScheme:ColorScheme.fromSeed(seedColor:teal,primary:teal),
      inputDecorationTheme:InputDecorationTheme(filled:true,fillColor:Colors.white,
        border:OutlineInputBorder(borderRadius:BorderRadius.circular(16)))),
    home:const Entry());
}
class Entry extends StatefulWidget {const Entry({super.key});@override State<Entry> createState()=>_EntryState();}
class _EntryState extends State<Entry>{
 bool entered=false,login=true;
 @override Widget build(BuildContext context)=>entered?Shell(exit:()=>setState(()=>entered=false)):
 Scaffold(body:SafeArea(child:Center(child:SingleChildScrollView(padding:const EdgeInsets.all(24),
 child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:440),child:Column(
 crossAxisAlignment:CrossAxisAlignment.stretch,children:[
 const CircleAvatar(radius:42,backgroundColor:teal,child:Icon(Icons.account_balance_wallet,color:Colors.white,size:42)),
 const SizedBox(height:20),const Text('Batlokoa Finance',textAlign:TextAlign.center,style:TextStyle(fontSize:31,fontWeight:FontWeight.bold,color:teal)),
 const Text('Borrow smarter. Pay easier.',textAlign:TextAlign.center),
 const SizedBox(height:28),CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
 Text(login?'Welcome back':'Create an account',style:const TextStyle(fontSize:23,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 if(!login)...[const TextField(decoration:InputDecoration(labelText:'Full name')),const SizedBox(height:12)],
 const TextField(keyboardType:TextInputType.phone,decoration:InputDecoration(labelText:'Phone number',prefixIcon:Icon(Icons.phone_outlined))),
 const SizedBox(height:12),
 const TextField(obscureText:true,decoration:InputDecoration(labelText:'Password',prefixIcon:Icon(Icons.lock_outline))),
 const SizedBox(height:18),
 FilledButton(onPressed:()=>setState(()=>entered=true),child:Text(login?'Sign in (demo)':'Register (demo)')),
 TextButton(onPressed:()=>setState(()=>login=!login),child:Text(login?'Create an account':'Already have an account?')),
 TextButton(onPressed:()=>setState(()=>entered=true),child:const Text('Explore demo')),
 ])),const SizedBox(height:14),
 const Text('Demo interface only. No real authentication or money transfers.',textAlign:TextAlign.center,style:TextStyle(fontSize:12)),
 ]))))));
}
class Shell extends StatefulWidget {final VoidCallback exit;const Shell({super.key,required this.exit});@override State<Shell> createState()=>_ShellState();}
class _ShellState extends State<Shell> {
 int tab=0;static const names=['Home','Loans','Wallet','Pay bills','Profile'];
 static const icons=[Icons.home_rounded,Icons.account_balance_rounded,Icons.wallet_rounded,Icons.grid_view_rounded,Icons.person_rounded];
 void navigate(Widget page)=>Navigator.push(context,MaterialPageRoute(builder:(_)=>page));
 @override Widget build(BuildContext context){
 final wide=MediaQuery.sizeOf(context).width>=800;
 final pages=<Widget>[
 Home(go:(v)=>setState(()=>tab=v),open:navigate),
 Loans(open:navigate),Wallet(open:navigate),Bills(open:navigate),
 Profile(open:navigate,exit:widget.exit)];
 return Scaffold(body:SafeArea(child:Row(children:[
 if(wide)NavigationRail(selectedIndex:tab,onDestinationSelected:(v)=>setState(()=>tab=v),
 extended:MediaQuery.sizeOf(context).width>1100,backgroundColor:Colors.white,
 leading:const Padding(padding:EdgeInsets.all(16),child:CircleAvatar(backgroundColor:teal,child:Icon(Icons.wallet,color:Colors.white))),
 destinations:[for(int i=0;i<names.length;i++)NavigationRailDestination(icon:Icon(icons[i]),label:Text(names[i]))]),
 Expanded(child:Center(child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:1100),
 child:KeyedSubtree(key:ValueKey(tab),child:pages[tab])))),
 ])),bottomNavigationBar:wide?null:NavigationBar(selectedIndex:tab,
 onDestinationSelected:(v)=>setState(()=>tab=v),destinations:[
 for(int i=0;i<names.length;i++)NavigationDestination(icon:Icon(icons[i]),label:names[i])]));}
}
class CardBox extends StatelessWidget{
 final Widget child;const CardBox({super.key,required this.child});
 @override Widget build(BuildContext context)=>Material(
   color:Colors.white,
   clipBehavior:Clip.antiAlias,
   shape:RoundedRectangleBorder(
     borderRadius:BorderRadius.circular(23),
     side:const BorderSide(color:Color(0xFFE4ECEA)),
   ),
   child:Padding(padding:const EdgeInsets.all(19),child:child),
 );
}
class Content extends StatelessWidget{
 final String title,subtitle;final List<Widget> children;
 const Content({super.key,required this.title,this.subtitle='',required this.children});
 @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(20),children:[
 Text(title,style:const TextStyle(fontSize:28,color:teal,fontWeight:FontWeight.w800)),
 if(subtitle.isNotEmpty)...[const SizedBox(height:4),Text(subtitle,style:const TextStyle(color:Colors.black54))],
 const SizedBox(height:20),
 for(final child in children)...[child,const SizedBox(height:16)],
 ]);
}
class ActionButton extends StatelessWidget{
 final String title;final VoidCallback onTap;const ActionButton(this.title,this.onTap,{super.key});
 @override Widget build(BuildContext context)=>SizedBox(width:double.infinity,height:50,
 child:FilledButton(onPressed:onTap,child:Text(title)));
}
void demo(BuildContext context,String label)=>showDialog<void>(context:context,builder:(ctx)=>AlertDialog(
 title:const Text('Demo preview'),content:Text(label+' is not connected to a financial service. No money moved or application submitted.'),
 actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('OK'))]));
class Home extends StatelessWidget{
 final ValueChanged<int> go;final ValueChanged<Widget> open;
 const Home({super.key,required this.go,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'Good morning 👋',subtitle:'Welcome to Batlokoa Finance',children:[
 Container(padding:const EdgeInsets.all(24),decoration:BoxDecoration(color:teal,borderRadius:BorderRadius.circular(24)),
 child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Available wallet balance',style:TextStyle(color:Colors.white70)),
 const SizedBox(height:8),const Text('M 2,450.00',style:TextStyle(color:Colors.white,fontSize:34,fontWeight:FontWeight.bold)),
 const Text('Sample balance • LSL',style:TextStyle(color:Colors.white70,fontSize:12)),
 const SizedBox(height:15),Wrap(spacing:8,children:[
 ActionChip(label:const Text('Add money'),onPressed:()=>open(const Transfer(action:'Add money'))),
 ActionChip(label:const Text('Send money'),onPressed:()=>open(const Transfer(action:'Send money')))]),
 ])),
 LayoutBuilder(builder:(context,c)=>c.maxWidth>=680?Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Expanded(child:loanSummary(context)),const SizedBox(width:15),Expanded(child:quickPayments(context))]):
 Column(children:[loanSummary(context),const SizedBox(height:16),quickPayments(context)])),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Recent activity',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 const Transaction('Electricity payment','28 Oct 2026','− M 200.00',Icons.bolt),
 const Divider(),const Transaction('Wallet top-up','26 Oct 2026','+ M 1,000.00',Icons.arrow_downward),
 TextButton(onPressed:()=>open(const History()),child:const Text('See all transactions'))
 ])),
 ]);
 Widget loanSummary(BuildContext context)=>CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('My active loan',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 const SizedBox(height:10),const Text('Outstanding balance'),
 const Text('M 5,800.00',style:TextStyle(fontSize:28,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:12),const LinearProgressIndicator(value:0.38,color:mint,backgroundColor:bg),
 const SizedBox(height:10),const Text('Next instalment M 650.00'),
 const SizedBox(height:15),ActionButton('Manage loan',()=>go(1))]));
 Widget quickPayments(BuildContext context)=>CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Quick payments',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 Services(onTap:(s)=>open(PayService(service:s)),compact:true)]));
}
class Loans extends StatelessWidget{
 final ValueChanged<Widget> open;const Loans({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'My loans',subtitle:'Borrowing and repayments',children:[
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Current balance'),const Text('M 5,800.00',style:TextStyle(fontSize:31,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:12),const Detail('Product','Personal loan'),const Detail('Status','Active'),
 const Detail('Next due','15 Nov 2026'),const Detail('Instalment','M 650.00'),
 const SizedBox(height:16),ActionButton('View loan details',()=>open(const LoanDetails()))])),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Apply for a loan',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
 const SizedBox(height:8),const Text('Select an amount and repayment period to begin.'),
 const SizedBox(height:16),ActionButton('Start application',()=>open(const ApplyLoan()))])),
 const CardBox(child:ListTile(contentPadding:EdgeInsets.zero,leading:Icon(Icons.check_circle,color:mint),
 title:Text('Previous personal loan'),subtitle:Text('Settled • 2025'),trailing:Text('M 3,000'))),
  ]);
}
class LoanDetails extends StatelessWidget{
 const LoanDetails({super.key});
 @override Widget build(BuildContext context)=>Subpage(title:'Loan details',child:CardBox(child:Column(
 crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Outstanding balance'),const Text('M 5,800.00',style:TextStyle(fontSize:32,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:16),const Detail('Reference','BTL-DEMO-1001'),
 const Detail('Instalment','M 650.00'),const Detail('Next due','15 Nov 2026'),
 const Detail('Status','Active'),const SizedBox(height:20),
 ActionButton('Repay loan',()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const Transfer(action:'Repay loan')))),
 const SizedBox(height:18),const Text('Upcoming instalments',style:TextStyle(fontWeight:FontWeight.bold)),
 const Detail('15 Nov 2026','M 650.00'),const Detail('15 Dec 2026','M 650.00'),
 const Detail('15 Jan 2027','M 650.00'),
  ])));
}
class ApplyLoan extends StatefulWidget{const ApplyLoan({super.key});@override State<ApplyLoan> createState()=>_ApplyLoanState();}
class _ApplyLoanState extends State<ApplyLoan>{
 int step=0,months=6;double amount=5000;String purpose='Personal';final income=TextEditingController();
 final incomeSource=TextEditingController();
 @override void dispose(){income.dispose();incomeSource.dispose();super.dispose();}
 @override Widget build(BuildContext context)=>Subpage(title:'Apply for a loan',child:CardBox(child:Column(
 crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text('Step '+(step+1).toString()+' of 3'),const SizedBox(height:8),
 LinearProgressIndicator(value:(step+1)/3),const SizedBox(height:22),
 if(step==0)...[
 const Text('Choose your loan',style:TextStyle(fontSize:21,fontWeight:FontWeight.bold)),
 const SizedBox(height:18),Text('Requested: M '+amount.round().toString()),
 Slider(min:500,max:20000,divisions:39,value:amount,onChanged:(v)=>setState(()=>amount=v)),
 DropdownButtonFormField<int>(initialValue:months,decoration:const InputDecoration(labelText:'Repayment term'),
 items:[3,6,9,12,18,24].map((m)=>DropdownMenuItem(value:m,child:Text(m.toString()+' months'))).toList(),
 onChanged:(v)=>setState(()=>months=v??months)),
 const SizedBox(height:12),
 DropdownButtonFormField<String>(initialValue:purpose,decoration:const InputDecoration(labelText:'Purpose'),
 items:['Personal','Education','Emergency','Business','Home'].map((s)=>DropdownMenuItem(value:s,child:Text(s))).toList(),
 onChanged:(v)=>setState(()=>purpose=v??purpose)),
 ]else if(step==1)...[
 const Text('Affordability details',style:TextStyle(fontSize:21,fontWeight:FontWeight.bold)),
 const SizedBox(height:14),TextField(controller:incomeSource,decoration:const InputDecoration(labelText:'Employment / income source')),
 const SizedBox(height:12),TextField(controller:income,keyboardType:TextInputType.number,
 decoration:const InputDecoration(labelText:'Monthly income in LSL')),
 ]else...[
 const Text('Review your request',style:TextStyle(fontSize:21,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),Detail('Amount','M '+amount.toStringAsFixed(2)),
 Detail('Term',months.toString()+' months'),Detail('Purpose',purpose),
 Detail('Income source',incomeSource.text.trim()),Detail('Monthly income','M '+income.text.trim()),
 const SizedBox(height:12),
 const Text('Not a loan offer. LoanHub must supply interest, fees, repayment schedule and mandatory disclosures before acceptance.'),
 ],
 const SizedBox(height:24),
 if(step>0)TextButton(onPressed:()=>setState(()=>step--),child:const Text('Back')),
 ActionButton(step==2?'Preview application':'Continue',(){
 if(step==1 && (incomeSource.text.trim().isEmpty || (double.tryParse(income.text.trim())??0)<=0)){
 ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Enter your income source and a valid monthly income.')));
 return;
 }
 if(step<2){setState(()=>step++);}else{demo(context,'Loan application');}
 }),
  ])));
}
class Wallet extends StatelessWidget{
 final ValueChanged<Widget> open;const Wallet({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'My wallet',subtitle:'Money management',children:[
 Container(padding:const EdgeInsets.all(24),decoration:BoxDecoration(color:teal,borderRadius:BorderRadius.circular(22)),
 child:const Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text('Available balance',style:TextStyle(color:Colors.white70)),
 SizedBox(height:10),Text('M 2,450.00',style:TextStyle(color:Colors.white,fontSize:34,fontWeight:FontWeight.bold)),
 Text('Demo funds • Not redeemable',style:TextStyle(color:Colors.white70))])),
 CardBox(child:Wrap(spacing:10,runSpacing:10,children:[
 for(final a in ['Add money','Send money','Withdraw','Repay loan'])
 OutlinedButton(onPressed:()=>open(Transfer(action:a)),child:Text(a))])),
 CardBox(child:Column(children:[
 const Transaction('Wallet top-up','26 Oct 2026','+ M 1,000.00',Icons.arrow_downward),
 const Divider(),const Transaction('LEC prepaid','28 Oct 2026','− M 200.00',Icons.bolt),
 TextButton(onPressed:()=>open(const History()),child:const Text('View all activity'))])),
  ]);
}
class Transfer extends StatefulWidget{final String action;const Transfer({super.key,required this.action});@override State<Transfer> createState()=>_TransferState();}
class _TransferState extends State<Transfer>{
 String method='M-Pesa';final form=GlobalKey<FormState>();
 final amountController=TextEditingController();final referenceController=TextEditingController();
 @override void dispose(){amountController.dispose();referenceController.dispose();super.dispose();}
 @override Widget build(BuildContext context)=>Subpage(title:widget.action,child:CardBox(child:Form(
 key:form,child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text(widget.action,style:const TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 DropdownButtonFormField<String>(initialValue:method,decoration:const InputDecoration(labelText:'Method'),
 items:['M-Pesa','Bank account','Wallet'].map((v)=>DropdownMenuItem(value:v,child:Text(v))).toList(),
 onChanged:(v)=>setState(()=>method=v??method)),
 if(widget.action!='Repay loan')...[const SizedBox(height:12),
 TextFormField(controller:referenceController,decoration:const InputDecoration(labelText:'Recipient / account number'),
 validator:DemoInputValidator.reference)],
 const SizedBox(height:12),
 TextFormField(controller:amountController,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'Amount in LSL'),
 validator:DemoInputValidator.amount),
 const SizedBox(height:15),
 const Text('Final transaction fees will come from IthutePay.',style:TextStyle(color:Colors.black54)),
 const SizedBox(height:20),
 ActionButton('Review transaction',(){if(form.currentState!.validate())Navigator.push(context,MaterialPageRoute(builder:(_)=>DemoPaymentReview(title:widget.action,amount:amountController.text.trim(),reference:widget.action=='Repay loan'?'BTL-DEMO-1001':referenceController.text.trim(),method:method)));}),
  ]))));
}
const serviceList=<({String name,IconData icon})>[
 (name:'Electricity',icon:Icons.bolt),(name:'WASCO water',icon:Icons.water_drop),
 (name:'Airtime',icon:Icons.phone_android),(name:'Mobile data',icon:Icons.wifi),
 (name:'TV subscriptions',icon:Icons.tv),(name:'School fees',icon:Icons.school),
 (name:'Transfers',icon:Icons.swap_horiz),(name:'More',icon:Icons.more_horiz)];
class Services extends StatelessWidget{
 final ValueChanged<String> onTap;final bool compact;
 const Services({super.key,required this.onTap,this.compact=false});
 @override Widget build(BuildContext context)=>LayoutBuilder(builder:(context,c)=>GridView.count(
 crossAxisCount:c.maxWidth<220?1:c.maxWidth>500?4:2,crossAxisSpacing:9,mainAxisSpacing:9,
 mainAxisExtent:(compact?100.0:112.0)*MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0,1.5).toDouble(),
 shrinkWrap:true,physics:const NeverScrollableScrollPhysics(),
 children:[for(final s in serviceList)InkWell(onTap:()=>onTap(s.name),borderRadius:BorderRadius.circular(14),
 child:Container(decoration:BoxDecoration(color:bg,borderRadius:BorderRadius.circular(14)),
 child:Column(mainAxisAlignment:MainAxisAlignment.center,children:[
 Icon(s.icon,color:teal,size:compact?23:29),const SizedBox(height:6),
 Text(s.name,textAlign:TextAlign.center,maxLines:2,style:const TextStyle(fontSize:12,fontWeight:FontWeight.w600)),
 ])))]));
}
class Bills extends StatelessWidget{
 final ValueChanged<Widget> open;const Bills({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'Pay bills',subtitle:'Utilities, airtime and more',children:[
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Choose a service',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 Services(onTap:(s){if(s=='Transfers'){open(const Transfer(action:'Send money'));}else if(s=='More'){demo(context,'More billers');}else{open(PayService(service:s));}}),
 ])),
 const CardBox(child:Text('External providers and bill lookup APIs are not yet connected. All payment flows are demos.')),
  ]);
}
class PayService extends StatefulWidget{final String service;const PayService({super.key,required this.service});@override State<PayService> createState()=>_PayServiceState();}
class _PayServiceState extends State<PayService>{
 final form=GlobalKey<FormState>();
 final amountController=TextEditingController(),referenceController=TextEditingController();
 @override void dispose(){amountController.dispose();referenceController.dispose();super.dispose();}
 @override Widget build(BuildContext context)=>Subpage(title:widget.service,child:CardBox(child:Form(key:form,
 child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text('Pay '+widget.service,style:const TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
 const SizedBox(height:18),
 TextFormField(controller:referenceController,decoration:InputDecoration(labelText:switch(widget.service){
 'Electricity'=>'Meter number','WASCO water'=>'Water account number','School fees'=>'Student reference',
 'TV subscriptions'=>'Subscriber number',_=>'Mobile phone number'}),
 validator:DemoInputValidator.reference),
 const SizedBox(height:12),
 TextFormField(controller:amountController,keyboardType:TextInputType.number,decoration:const InputDecoration(labelText:'Amount in LSL'),
 validator:DemoInputValidator.amount),
 const SizedBox(height:16),
 const Text('Biller validation, settlement and receipts require an approved provider integration.'),
 const SizedBox(height:18),
 ActionButton('Review payment',(){if(form.currentState!.validate())Navigator.push(context,MaterialPageRoute(builder:(_)=>DemoPaymentReview(title:widget.service,amount:amountController.text.trim(),reference:referenceController.text.trim(),method:'Wallet (demo)')));}),
  ]))));
}
class Profile extends StatelessWidget{
 final ValueChanged<Widget> open;final VoidCallback exit;
 const Profile({super.key,required this.open,required this.exit});
 @override Widget build(BuildContext context)=>Content(title:'My profile',subtitle:'Your account and security',children:[
 const CardBox(child:ListTile(contentPadding:EdgeInsets.zero,
 leading:CircleAvatar(backgroundColor:bg,child:Icon(Icons.person,color:teal)),
 title:Text('Demo Customer'),subtitle:Text('Not verified • Sample account'))),
 CardBox(child:Column(children:[
 for(final item in <({String name,IconData icon,String text})>[
 (name:'Personal information',icon:Icons.person_outline,text:'Verified customer information will appear here.'),
 (name:'Identity verification',icon:Icons.verified_user_outlined,text:'KYC and document uploads will connect to the identity service.'),
 (name:'Security settings',icon:Icons.shield_outlined,text:'Production authentication and device management will be enabled after integration.'),
 (name:'Notifications',icon:Icons.notifications_outlined,text:'Payment and loan notifications will appear here.'),
 (name:'Help and support',icon:Icons.help_outline,text:'Customer support and complaints workflows will be available here.'),
 (name:'About Batlokoa',icon:Icons.info_outline,text:'Batlokoa Finance • batlokoa.co.ls\nPowered by LoanHub + IthutePay.')])
 ListTile(contentPadding:EdgeInsets.zero,leading:Icon(item.icon,color:teal),title:Text(item.name),
 trailing:const Icon(Icons.chevron_right),onTap:()=>open(item.name=='Identity verification'?const VerifyCustomer():item.name=='Security settings'?const AccountPreferences():item.name=='Notifications'?const AlertsPage():item.name=='Help and support'?const HelpCentre():Info(title:item.name,body:item.text))),
 ListTile(contentPadding:EdgeInsets.zero,leading:const Icon(Icons.receipt_long,color:teal),
 title:const Text('Transaction history'),trailing:const Icon(Icons.chevron_right),onTap:()=>open(const History())),
 ])),
 OutlinedButton.icon(onPressed:exit,icon:const Icon(Icons.logout),label:const Text('Exit demo')),
  ]);
}
class Subpage extends StatelessWidget{
 final String title;final Widget child;const Subpage({super.key,required this.title,required this.child});
 @override Widget build(BuildContext context)=>Scaffold(appBar:AppBar(title:Text(title)),
 body:SafeArea(child:Center(child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:740),
 child:ListView(padding:const EdgeInsets.all(20),children:[child])))));
}
class Detail extends StatelessWidget{
 final String label,value;const Detail(this.label,this.value,{super.key});
 @override Widget build(BuildContext context)=>Padding(padding:const EdgeInsets.symmetric(vertical:8),child:Row(children:[
 Expanded(child:Text(label,style:const TextStyle(color:Colors.black54))),
 Flexible(child:Text(value,textAlign:TextAlign.end,style:const TextStyle(fontWeight:FontWeight.bold)))]));
}
class Transaction extends StatelessWidget{
 final String title,date,amount;final IconData icon;
 final VoidCallback? onTap;
 const Transaction(this.title,this.date,this.amount,this.icon,{super.key,this.onTap});
 @override Widget build(BuildContext context)=>ListTile(contentPadding:EdgeInsets.zero,
 leading:CircleAvatar(backgroundColor:bg,child:Icon(icon,color:teal)),
 title:Text(title),subtitle:Text(date),onTap:onTap,trailing:Text(amount,style:const TextStyle(fontWeight:FontWeight.bold)));
}
class History extends StatelessWidget{
 const History({super.key});
 @override Widget build(BuildContext context)=>const ActivityHistoryPage();
}
class Info extends StatelessWidget{
 final String title,body;const Info({super.key,required this.title,required this.body});
 @override Widget build(BuildContext context)=>Subpage(title:title,child:CardBox(child:Text(body,style:const TextStyle(fontSize:16,height:1.6))));
}
