import 'package:flutter/material.dart';
import 'batlokoa_design.dart';
import 'demo_finance_components.dart';
import 'demo_draft_guard.dart';
import 'demo_form_error.dart';
import 'demo_loan_progress.dart';
import 'customer_flows.dart';
import 'payment_review.dart';
import 'activity_history.dart';
import 'input_validators.dart';
import 'customer_loans_screen.dart';
import 'customer_session_screen.dart';

void main() => runApp(const BatlokoaApp());
// Legacy aliases preserve the existing demo presentation while shared tokens
// provide one upgrade point for approved branding.
const teal=BatlokoaDesign.primary, mint=BatlokoaDesign.accent, bg=BatlokoaDesign.canvas;
class BatlokoaApp extends StatelessWidget {
  const BatlokoaApp({super.key});
  @override Widget build(BuildContext context)=>MaterialApp(
    debugShowCheckedModeBanner:false,title:'Batlokoa Finance',
    theme:BatlokoaDesign.theme(),
    home:const Entry());
}
class Entry extends StatefulWidget {const Entry({super.key});@override State<Entry> createState()=>_EntryState();}
class _EntryState extends State<Entry>{
 bool entered=false,login=true,passwordVisible=false;
 @override Widget build(BuildContext context)=>entered?Shell(exit:()=>setState(()=>entered=false)):
 Scaffold(body:SafeArea(child:Center(child:SingleChildScrollView(padding:const EdgeInsets.all(24),
 child:ConstrainedBox(constraints:const BoxConstraints(maxWidth:440),child:Column(
 crossAxisAlignment:CrossAxisAlignment.stretch,children:[
 const CircleAvatar(radius:42,backgroundColor:teal,child:Icon(Icons.account_balance_wallet,color:Colors.white,size:42)),
 const SizedBox(height:20),Text('Batlokoa Finance',textAlign:TextAlign.center,style:Theme.of(context).textTheme.headlineMedium),
 const Text('Borrow smarter. Pay easier.',textAlign:TextAlign.center),
 const SizedBox(height:28),CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.stretch,children:[
 Text(login?'Welcome back':'Create an account',style:const TextStyle(fontSize:23,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 if(!login)...[const TextField(textInputAction:TextInputAction.next,decoration:InputDecoration(labelText:'Full name')),const SizedBox(height:12)],
 const TextField(keyboardType:TextInputType.phone,textInputAction:TextInputAction.next,decoration:InputDecoration(labelText:'Phone number',prefixIcon:Icon(Icons.phone_outlined))),
 const SizedBox(height:12),
 TextField(
   obscureText:!passwordVisible,
   textInputAction:TextInputAction.done,
   decoration:InputDecoration(labelText:'Password',
     prefixIcon:const Icon(Icons.lock_outline),
     suffixIcon:IconButton(
       tooltip:passwordVisible?'Hide password':'Show password',
       icon:Icon(passwordVisible?Icons.visibility_off_outlined:Icons.visibility_outlined),
       onPressed:()=>setState(()=>passwordVisible=!passwordVisible),
     )),
 ),
 const SizedBox(height:18),
 FilledButton(onPressed:()=>setState(()=>entered=true),child:Text(login?'Preview sign in (demo)':'Preview registration (demo)')),
 TextButton(onPressed:()=>setState(()=>login=!login),child:Text(login?'Create an account':'Already have an account?')),
 TextButton(onPressed:()=>setState(()=>entered=true),child:const Text('Explore demo')),
 TextButton(onPressed:()=>Navigator.push(context,MaterialPageRoute<void>(builder:(_)=>const CustomerSessionScreen())),child:const Text('Secure sign-in status')),
 ])),const SizedBox(height:14),
 const DemoNotice(message:'This is a design preview. Entered credentials are not submitted or verified. No real authentication or money transfers.'),
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
 child:IndexedStack(index:tab,children:pages)))),
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
     borderRadius:BorderRadius.circular(BatlokoaDesign.cardRadius),
     side:const BorderSide(color:BatlokoaDesign.border),
   ),
   child:Padding(padding:const EdgeInsets.all(20),child:child),
 );
}
/// Always-visible disclosure on every main demo tab.
class DemoNotice extends StatelessWidget {
 final String message;
 const DemoNotice({
   super.key,
   this.message='DEMO PREVIEW — Balances, history and account details are fictional. No real payments or loan applications are enabled.',
 });
 @override Widget build(BuildContext context)=>Semantics(
   label:message,
   child:Container(
     width:double.infinity,
     padding:const EdgeInsets.symmetric(horizontal:14,vertical:12),
     decoration:BoxDecoration(
       color:const Color(0xFFFFF5DF),
       border:Border.all(color:const Color(0xFFE8D3A1)),
       borderRadius:BorderRadius.circular(12),
     ),
     child:Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
       const Icon(Icons.info_outline,color:Color(0xFF664D03),size:20),
       const SizedBox(width:10),
       Expanded(child:Text(message,style:const TextStyle(
         color:Color(0xFF664D03),fontSize:13,fontWeight:FontWeight.w600))),
     ]),
   ),
 );
}
class Content extends StatelessWidget{
 final String title,subtitle;final List<Widget> children;
 const Content({super.key,required this.title,this.subtitle='',required this.children});
 @override Widget build(BuildContext context)=>ListView(padding:BatlokoaDesign.pagePadding(MediaQuery.sizeOf(context).width),children:[
 Text(title,style:Theme.of(context).textTheme.headlineMedium),
 if(subtitle.isNotEmpty)...[const SizedBox(height:4),Text(subtitle,style:const TextStyle(color:Colors.black54))],
 const SizedBox(height:16),
 const DemoNotice(),
 const SizedBox(height:20),
 for(final child in children)...[child,const SizedBox(height:16)],
 ]);
}
class ActionButton extends StatelessWidget{
 final String title;final VoidCallback onTap;const ActionButton(this.title,this.onTap,{super.key});
 @override Widget build(BuildContext context)=>SizedBox(width:double.infinity,
 child:FilledButton(onPressed:onTap,child:Padding(
   padding:const EdgeInsets.symmetric(vertical:12),
   child:Text(title,textAlign:TextAlign.center))));
}
/// Resolve demo bill shortcuts consistently on Home and Pay bills.
/// No live biller, wallet or payment service is invoked.
void openDemoService(BuildContext context,String service,ValueChanged<Widget> open){
 if(service=='Transfers'){
   open(const Transfer(action:'Send money'));
 }else if(service=='More'){
   demo(context,'More billers');
 }else{
   open(PayService(service:service));
 }
}
void demo(BuildContext context,String label)=>showDialog<void>(context:context,builder:(ctx)=>AlertDialog(
 title:const Text('Demo preview'),content:Text(label+' is not connected to a financial service. No money moved or application submitted.'),
 actions:[TextButton(onPressed:()=>Navigator.pop(ctx),child:const Text('OK'))]));
class Home extends StatelessWidget{
 final ValueChanged<int> go;final ValueChanged<Widget> open;
 const Home({super.key,required this.go,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'Good morning 👋',subtitle:'Welcome to Batlokoa Finance',children:[
 DemoBalanceCard(
 label:'Sample wallet balance',
 amount:'M 2,450.00',
 disclaimer:'Fictional LSL funds • No transactions are processed',
 actions:Wrap(spacing:8,runSpacing:8,children:[
 ActionChip(label:const Text('Add money'),onPressed:()=>open(const Transfer(action:'Add money'))),
 ActionChip(label:const Text('Send money'),onPressed:()=>open(const Transfer(action:'Send money'))),
 ])),
 LayoutBuilder(builder:(context,c)=>c.maxWidth>=680?Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Expanded(child:loanSummary(context)),const SizedBox(width:15),Expanded(child:quickPayments(context))]):
 Column(children:[loanSummary(context),const SizedBox(height:16),quickPayments(context)])),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Sample recent activity',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 Transaction('Electricity payment','28 Oct 2026','− M 200.00',Icons.bolt,onTap:()=>open(const History())),
 const Divider(),Transaction('Wallet top-up','26 Oct 2026','+ M 1,000.00',Icons.arrow_downward,onTap:()=>open(const History())),
 TextButton(onPressed:()=>open(const History()),child:const Text('See all transactions'))
 ])),
 ]);
 Widget loanSummary(BuildContext context)=>CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('My active loan',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 const Text('Demo amounts only',style:TextStyle(fontSize:12,color:Colors.black54)),
 const SizedBox(height:10),const Text('Outstanding balance'),
 const Text('M 5,800.00',style:TextStyle(fontSize:28,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:12),const LinearProgressIndicator(value:0.38,color:mint,backgroundColor:bg),
 const SizedBox(height:10),const Text('Illustrative repayment progress: 38%'),
 const SizedBox(height:8),const Text('Sample next instalment: M 650.00'),
 const SizedBox(height:15),ActionButton('Manage loan',()=>go(1))]));
 Widget quickPayments(BuildContext context)=>CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Quick payments',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold)),
 Services(onTap:(s)=>openDemoService(context,s,open),compact:true)]));
}
class Loans extends StatelessWidget{
 final ValueChanged<Widget> open;const Loans({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'My loans',subtitle:'Borrowing and repayments',children:[
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Sample loan balance (demo)'),const Text('M 5,800.00',style:TextStyle(fontSize:31,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:12),const Detail('Product','Personal loan'),const Detail('Status','Active'),
 const Detail('Next due','15 Nov 2026'),const Detail('Instalment','M 650.00'),
 const SizedBox(height:16),ActionButton('View loan details',()=>open(const LoanDetails()))])),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Apply for a loan',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
 const SizedBox(height:8),const Text('Select an amount and repayment period to begin.'),
 const SizedBox(height:16),ActionButton('Start application',()=>open(const ApplyLoan()))])),
 const CardBox(child:ListTile(contentPadding:EdgeInsets.zero,leading:Icon(Icons.check_circle,color:mint),
 title:Text('Previous personal loan'),subtitle:Text('Settled • 2025'),trailing:Text('M 3,000'))),
 const Text('All loan balances and repayment dates above are fictional examples.'),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('My verified loans',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
 const SizedBox(height:8),
 const Text('Live loan information requires customer authentication and an approved LoanHub session. No demo balances are shown in the verified-loan view.'),
 const SizedBox(height:14),
 ActionButton('View verified loans',()=>open(const CustomerLoansScreen())),
 ])),
 const Text('DEMO LOANS ONLY — No real borrower account is linked to this preview.',
 style:TextStyle(fontWeight:FontWeight.w600)),

  ]);
}
class LoanDetails extends StatelessWidget{
 const LoanDetails({super.key});
 @override Widget build(BuildContext context)=>Subpage(title:'Loan details',child:CardBox(child:Column(
 crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Outstanding balance (demo)'),const Text('M 5,800.00',style:TextStyle(fontSize:32,fontWeight:FontWeight.bold,color:teal)),
 const SizedBox(height:16),const Detail('Reference','BTL-DEMO-1001'),
 const Detail('Instalment','M 650.00'),const Detail('Next due','15 Nov 2026'),
 const Detail('Status','Active'),const SizedBox(height:20),
 ActionButton('Repay loan',()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const Transfer(action:'Repay loan')))),
 const SizedBox(height:18),const DemoRepaymentPreview(),
 const SizedBox(height:12),
 OutlinedButton.icon(onPressed:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>const History())),
   icon:const Icon(Icons.history),label:const Text('View sample activity')),
 TextButton.icon(onPressed:()=>Navigator.pop(context),
   icon:const Icon(Icons.arrow_back),label:const Text('Back to loans')),
  ])));
}
class ApplyLoan extends StatefulWidget{const ApplyLoan({super.key});@override State<ApplyLoan> createState()=>_ApplyLoanState();}
class _ApplyLoanState extends State<ApplyLoan>{
 int step=0,months=6;double amount=5000;String purpose='Personal';String? formError;bool showFieldErrors=false;final income=TextEditingController();
 final incomeFocus=FocusNode(),incomeSourceFocus=FocusNode();
 final incomeSource=TextEditingController();
 @override void dispose(){income.dispose();incomeSource.dispose();incomeFocus.dispose();incomeSourceFocus.dispose();super.dispose();}
 bool get hasDraft=>step>0 || amount!=5000 || months!=6 || purpose!='Personal' || income.text.isNotEmpty || incomeSource.text.isNotEmpty;
 @override Widget build(BuildContext context)=>DemoDraftGuard(hasDraft:hasDraft,child:Subpage(title:'Apply for a loan',child:CardBox(child:Column(
 crossAxisAlignment:CrossAxisAlignment.start,children:[
 DemoLoanProgress(step:step),const SizedBox(height:22),
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
 const SizedBox(height:14),TextField(controller:incomeSource,focusNode:incomeSourceFocus,onChanged:(_)=>setState(()=>formError=null),textInputAction:TextInputAction.next,onSubmitted:(_)=>incomeFocus.requestFocus(),decoration:InputDecoration(labelText:'Employment / income source',errorText:showFieldErrors?DemoInputValidator.incomeSource(incomeSource.text):null)),
 const SizedBox(height:12),TextField(controller:income,focusNode:incomeFocus,onChanged:(_)=>setState(()=>formError=null),keyboardType:const TextInputType.numberWithOptions(decimal:true),textInputAction:TextInputAction.done,
 decoration:InputDecoration(labelText:'Monthly income in LSL',errorText:showFieldErrors?DemoInputValidator.monthlyIncome(income.text):null)),
 ]else...[
 const Text('Review your request',style:TextStyle(fontSize:21,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),Detail('Amount','M '+amount.toStringAsFixed(2)),
 Detail('Term',months.toString()+' months'),Detail('Purpose',purpose),
 Detail('Income source',incomeSource.text.trim()),Detail('Monthly income','M '+income.text.trim()),
 const SizedBox(height:12),
 const Text('Not a loan offer. LoanHub must supply interest, fees, repayment schedule and mandatory disclosures before acceptance.'),
 ],
 if(formError!=null)...[
 const SizedBox(height:14),DemoFormError(message:formError!),
 ],
 const SizedBox(height:24),
 if(step>0)TextButton(onPressed:()=>setState(()=>step--),child:const Text('Back')),
 ActionButton(step==2?'Preview application':'Continue',(){
 if(step==1){
 final sourceError=DemoInputValidator.incomeSource(incomeSource.text);
 final incomeError=DemoInputValidator.monthlyIncome(income.text);
 if(sourceError!=null || incomeError!=null){
 setState((){showFieldErrors=true;formError='Enter your income source and a valid monthly income.';});
 (sourceError!=null?incomeSourceFocus:incomeFocus).requestFocus();
 return;
 }
 }
 if(step<2){setState((){formError=null;showFieldErrors=false;step++;});}else{demo(context,'Loan application');}
 }),
  ]))));
}
class Wallet extends StatelessWidget{
 final ValueChanged<Widget> open;const Wallet({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'My wallet',subtitle:'Money management',children:[
 const DemoBalanceCard(
 label:'Sample wallet balance',
 amount:'M 2,450.00',
 disclaimer:'Fictional amount • Not available for withdrawal'),
 CardBox(child:DemoWalletActions(
 onAction:(action)=>open(Transfer(action:action)))),
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
 bool get hasDraft=>method!='M-Pesa' || amountController.text.isNotEmpty || referenceController.text.isNotEmpty;
 @override Widget build(BuildContext context)=>DemoDraftGuard(hasDraft:hasDraft,child:Subpage(title:widget.action,child:CardBox(child:Form(
 key:form,autovalidateMode:AutovalidateMode.onUserInteraction,child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text(widget.action,style:const TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 DropdownButtonFormField<String>(initialValue:method,decoration:const InputDecoration(labelText:'Method'),
 items:['M-Pesa','Bank account','Wallet'].map((v)=>DropdownMenuItem(value:v,child:Text(v))).toList(),
 onChanged:(v)=>setState(()=>method=v??method)),
 if(widget.action!='Repay loan')...[const SizedBox(height:12),
 TextFormField(controller:referenceController,onChanged:(_)=>setState((){}),textInputAction:TextInputAction.next,decoration:const InputDecoration(labelText:'Recipient / account number'),
 validator:DemoInputValidator.reference)],
 const SizedBox(height:12),
 TextFormField(controller:amountController,onChanged:(_)=>setState((){}),keyboardType:const TextInputType.numberWithOptions(decimal:true),textInputAction:TextInputAction.done,decoration:const InputDecoration(labelText:'Amount in LSL'),
 validator:DemoInputValidator.amount),
 const SizedBox(height:15),
 const Text('Final transaction fees will come from IthutePay.',style:TextStyle(color:Colors.black54)),
 const SizedBox(height:20),
 ActionButton('Review transaction',(){if(form.currentState!.validate())Navigator.push(context,MaterialPageRoute(builder:(_)=>DemoPaymentReview(title:widget.action,amount:amountController.text.trim(),reference:widget.action=='Repay loan'?'BTL-DEMO-1001':referenceController.text.trim(),method:method)));}),
  ])))));
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
 mainAxisExtent:(compact?106.0:122.0)*MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0,2.0).toDouble(),
 shrinkWrap:true,physics:const NeverScrollableScrollPhysics(),
 children:[for(final s in serviceList)InkWell(onTap:()=>onTap(s.name),borderRadius:BorderRadius.circular(14),
 child:Container(padding:const EdgeInsets.symmetric(horizontal:6),decoration:BoxDecoration(color:bg,borderRadius:BorderRadius.circular(14)),
 child:Column(mainAxisAlignment:MainAxisAlignment.center,children:[
 Icon(s.icon,color:teal,size:compact?23:29),const SizedBox(height:6),
 Text(s.name,textAlign:TextAlign.center,maxLines:3,overflow:TextOverflow.ellipsis,style:const TextStyle(fontSize:12,fontWeight:FontWeight.w600)),
 ])))]));
}
class Bills extends StatelessWidget{
 final ValueChanged<Widget> open;const Bills({super.key,required this.open});
 @override Widget build(BuildContext context)=>Content(title:'Pay bills',subtitle:'Utilities, airtime and more',children:[
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Text('Choose a service',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
 const SizedBox(height:16),
 Services(onTap:(s)=>openDemoService(context,s,open)),
 ])),
 const CardBox(child:Text('External providers and bill lookup APIs are not yet connected. All payment flows are demos.')),
  ]);
}
class PayService extends StatefulWidget{final String service;const PayService({super.key,required this.service});@override State<PayService> createState()=>_PayServiceState();}
class _PayServiceState extends State<PayService>{
 final form=GlobalKey<FormState>();
 final amountController=TextEditingController(),referenceController=TextEditingController();
 @override void dispose(){amountController.dispose();referenceController.dispose();super.dispose();}
 bool get hasDraft=>amountController.text.isNotEmpty || referenceController.text.isNotEmpty;
 @override Widget build(BuildContext context)=>DemoDraftGuard(hasDraft:hasDraft,child:Subpage(title:widget.service,child:CardBox(child:Form(key:form,autovalidateMode:AutovalidateMode.onUserInteraction,
 child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 Text('Pay '+widget.service,style:const TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
 const SizedBox(height:18),
 TextFormField(controller:referenceController,onChanged:(_)=>setState((){}),textInputAction:TextInputAction.next,decoration:InputDecoration(labelText:switch(widget.service){
 'Electricity'=>'Meter number','WASCO water'=>'Water account number','School fees'=>'Student reference',
 'TV subscriptions'=>'Subscriber number',_=>'Mobile phone number'}),
 validator:DemoInputValidator.reference),
 const SizedBox(height:12),
 TextFormField(controller:amountController,onChanged:(_)=>setState((){}),keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'Amount in LSL'),
 validator:DemoInputValidator.amount),
 const SizedBox(height:16),
 const Text('Biller validation, settlement and receipts require an approved provider integration.'),
 const SizedBox(height:18),
 ActionButton('Review payment',(){if(form.currentState!.validate())Navigator.push(context,MaterialPageRoute(builder:(_)=>DemoPaymentReview(title:widget.service,amount:amountController.text.trim(),reference:referenceController.text.trim(),method:'Wallet (demo)')));}),
  ])))));
}
class Profile extends StatelessWidget{
 final ValueChanged<Widget> open;final VoidCallback exit;
 const Profile({super.key,required this.open,required this.exit});
 @override Widget build(BuildContext context)=>Content(title:'My profile',subtitle:'Your account and security',children:[
 const CardBox(child:ListTile(contentPadding:EdgeInsets.zero,
 leading:CircleAvatar(backgroundColor:bg,child:Icon(Icons.person,color:teal)),
 title:Text('Demo Customer'),subtitle:Text('Not verified • Sample account'),
 trailing:Icon(Icons.lock_outline,color:teal))),
 CardBox(child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
 const Padding(padding:EdgeInsets.only(bottom:12),child:Text('Account and support',style:TextStyle(fontSize:18,fontWeight:FontWeight.bold))),
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
/// Key-value details stack at large text size or constrained card width.
class Detail extends StatelessWidget{
 final String label,value;const Detail(this.label,this.value,{super.key});
 @override Widget build(BuildContext context)=>LayoutBuilder(
   builder:(context,constraints){
     final stacked=constraints.maxWidth<300 ||
       MediaQuery.textScalerOf(context).scale(1.0)>1.35;
     final labelWidget=Text(label,style:const TextStyle(color:Colors.black54));
     final valueWidget=Text(value,
       textAlign:stacked?TextAlign.start:TextAlign.end,
       style:const TextStyle(fontWeight:FontWeight.bold));
     return Padding(padding:const EdgeInsets.symmetric(vertical:8),
       child:stacked?Column(crossAxisAlignment:CrossAxisAlignment.start,
         children:[labelWidget,const SizedBox(height:4),valueWidget]):
         Row(crossAxisAlignment:CrossAxisAlignment.start,children:[
           Expanded(child:labelWidget),
           const SizedBox(width:12),
           Flexible(child:valueWidget),
         ]));
   });
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
