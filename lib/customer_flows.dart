import 'package:flutter/material.dart';

class ExtrasPage extends StatelessWidget {
  final String title;
  final Widget child;
  const ExtrasPage({super.key,required this.title,required this.child});
  @override Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:Text(title)),
    body:SafeArea(child:Center(child:ConstrainedBox(
      constraints:const BoxConstraints(maxWidth:740),
      child:ListView(padding:const EdgeInsets.all(20),children:[
        Card(color:Colors.white,child:Padding(padding:const EdgeInsets.all(20),child:child))
      ])))));
}

void previewNotice(BuildContext context,String name)=>showDialog<void>(
  context:context,builder:(dialog)=>AlertDialog(
    title:const Text('Demo only'),
    content:Text(name+' is a preview and is not submitted to Batlokoa.'),
    actions:[TextButton(onPressed:()=>Navigator.pop(dialog),child:const Text('OK'))],
  ),
);

class VerifyCustomer extends StatefulWidget{
  const VerifyCustomer({super.key});
  @override State<VerifyCustomer> createState()=>_VerifyCustomerState();
}
class _VerifyCustomerState extends State<VerifyCustomer>{
  int step=0;bool consent=false;String document='National ID';
  @override Widget build(BuildContext context)=>ExtrasPage(title:'Identity verification',
    child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
      const Text('Verify your identity',style:TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
      const SizedBox(height:8),const Text('Preview only — do not submit actual identity information.'),
      const SizedBox(height:18),
      Text('Step '+(step+1).toString()+' of 3'),
      const SizedBox(height:8),LinearProgressIndicator(value:(step+1)/3),
      const SizedBox(height:18),
      if(step==0)...[
        const Text('Choose your document type'),
        const SizedBox(height:12),
        DropdownButtonFormField<String>(initialValue:document,
          decoration:const InputDecoration(labelText:'Document'),
          items:['National ID','Passport'].map((item)=>DropdownMenuItem(value:item,child:Text(item))).toList(),
          onChanged:(value)=>setState(()=>document=value??document)),
        const ListTile(contentPadding:EdgeInsets.zero,leading:Icon(Icons.camera_alt_outlined),
          title:Text('Capture identity document'),subtitle:Text('Not connected in demo mode')),
      ]else if(step==1)...[
        const ListTile(contentPadding:EdgeInsets.zero,leading:Icon(Icons.face_outlined),
          title:Text('Selfie and liveness check'),subtitle:Text('Camera verification will be added with a KYC provider')),
        const ListTile(contentPadding:EdgeInsets.zero,leading:Icon(Icons.shield_outlined),
          title:Text('Secure document handling'),subtitle:Text('Encrypted storage and consent required')),
      ]else...[
        Text('Document type: '+document),
        CheckboxListTile(contentPadding:EdgeInsets.zero,value:consent,
          onChanged:(v)=>setState(()=>consent=v??false),
          title:const Text('I have read the privacy notice'),
          subtitle:const Text('A complete privacy notice must be provided before launch')),
      ],
      const SizedBox(height:15),
      Wrap(spacing:12,children:[
        if(step>0)OutlinedButton(onPressed:()=>setState(()=>step--),child:const Text('Back')),
        FilledButton(onPressed:step==2&&!consent?null:(){
          if(step<2){setState(()=>step++);}else{previewNotice(context,'Verification');}
        },child:Text(step==2?'Preview verification':'Continue')),
      ]),
  ]));
}

class AlertsPage extends StatefulWidget{
 const AlertsPage({super.key});
 @override State<AlertsPage> createState()=>_AlertsPageState();
}
class _AlertsPageState extends State<AlertsPage>{
 bool unreadOnly=false;
 @override Widget build(BuildContext context)=>ExtrasPage(title:'Notifications',child:Column(children:[
  SwitchListTile.adaptive(title:const Text('Unread only'),value:unreadOnly,
    onChanged:(v)=>setState(()=>unreadOnly=v)),
  const Divider(),
  const ListTile(leading:Icon(Icons.event_outlined),title:Text('Upcoming loan payment'),
    subtitle:Text('Demo: M 650.00 due 15 Nov 2026')),
  const Divider(),
  const ListTile(leading:Icon(Icons.shield_outlined),title:Text('Security reminder'),
    subtitle:Text('Never share your password or OTP')),
  if(!unreadOnly)...[
    const Divider(),
    const ListTile(leading:Icon(Icons.receipt_outlined),title:Text('Sample bill payment'),
      subtitle:Text('Electricity transaction • Demo history')),
  ],
 ]));
}

class AccountPreferences extends StatefulWidget{
 const AccountPreferences({super.key});
 @override State<AccountPreferences> createState()=>_AccountPreferencesState();
}
class _AccountPreferencesState extends State<AccountPreferences>{
 bool biometric=false,notifications=true,promotions=false;
 @override Widget build(BuildContext context)=>ExtrasPage(title:'Security & preferences',
 child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
   const Text('Security',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
   SwitchListTile.adaptive(contentPadding:EdgeInsets.zero,title:const Text('Biometric sign-in'),
     subtitle:const Text('Demo setting only'),value:biometric,onChanged:(v)=>setState(()=>biometric=v)),
   ListTile(contentPadding:EdgeInsets.zero,title:const Text('Change password'),
     leading:const Icon(Icons.lock_reset),trailing:const Icon(Icons.chevron_right),
     onTap:()=>previewNotice(context,'Password change')),
   ListTile(contentPadding:EdgeInsets.zero,title:const Text('Manage devices'),
     leading:const Icon(Icons.devices),trailing:const Icon(Icons.chevron_right),
     onTap:()=>previewNotice(context,'Device management')),
   const Divider(),
   const Text('Notifications',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
   SwitchListTile.adaptive(contentPadding:EdgeInsets.zero,title:const Text('Transaction alerts'),
     value:notifications,onChanged:(v)=>setState(()=>notifications=v)),
   SwitchListTile.adaptive(contentPadding:EdgeInsets.zero,title:const Text('Marketing updates'),
     value:promotions,onChanged:(v)=>setState(()=>promotions=v)),
   const Text('Preferences are not saved between sessions.',style:TextStyle(fontSize:12)),
 ]));
}

class HelpCentre extends StatefulWidget{
 const HelpCentre({super.key});
 @override State<HelpCentre> createState()=>_HelpCentreState();
}
class _HelpCentreState extends State<HelpCentre>{
 String topic='Loans';final question=TextEditingController();
 @override void dispose(){question.dispose();super.dispose();}
 @override Widget build(BuildContext context)=>ExtrasPage(title:'Help & support',
 child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
   const Text('How can we help?',style:TextStyle(fontSize:22,fontWeight:FontWeight.bold)),
   const SizedBox(height:8),const Text('Preview only — no message is sent.'),
   const SizedBox(height:16),
   DropdownButtonFormField<String>(initialValue:topic,decoration:const InputDecoration(labelText:'Topic'),
     items:['Loans','Payments','Account access','Disputes','Other'].map((s)=>
       DropdownMenuItem(value:s,child:Text(s))).toList(),
     onChanged:(v)=>setState(()=>topic=v??topic)),
   const SizedBox(height:12),
   TextField(controller:question,maxLines:5,maxLength:1000,
     onChanged:(_)=>setState((){}),
     decoration:const InputDecoration(labelText:'Your question',alignLabelWithHint:true)),
   const SizedBox(height:12),
   SizedBox(width:double.infinity,child:FilledButton(
     onPressed:question.text.trim().isEmpty?null:()=>previewNotice(context,'Support request'),
     child:const Text('Preview support request'))),
   const SizedBox(height:20),
   const Text('Common questions',style:TextStyle(fontSize:20,fontWeight:FontWeight.bold)),
   const ExpansionTile(title:Text('How do I apply for a loan?'),
     children:[Padding(padding:EdgeInsets.all(12),child:Text('Visit Loans and select Start application.'))]),
   const ExpansionTile(title:Text('Where do I see my repayments?'),
     children:[Padding(padding:EdgeInsets.all(12),child:Text('Open Loans, then View loan details.'))]),
   const ExpansionTile(title:Text('Are payments live?'),
     children:[Padding(padding:EdgeInsets.all(12),child:Text('No. Payments are currently demonstrations.'))]),
 ]));
}
