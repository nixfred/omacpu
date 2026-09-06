import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
    id: root
    moduleName: 'nixfred.cpu-pulse'
    ipcTarget: 'nixfred.cpu-pulse'
    manageIpc: false
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    readonly property string stateDir: (Quickshell.env('XDG_STATE_HOME') || Quickshell.env('HOME')+'/.local/state')+'/cpu-pulse'
    readonly property string helper: decodeURIComponent(String(Qt.resolvedUrl('cpu_pulse.py')).replace(/^file:\/\//,''))
    property var cpu: ({})
    property var histories: ({})
    property int tab: 0
    property int page: 0
    property int range: 3600
    property bool chooseMode: false
    property string actionStatus: ''
    property real now: Date.now()/1000
    readonly property bool stale: !cpu.ts || now-cpu.ts > 15
    readonly property int mode: Model.clamp(setting('displayMode',0),0,3)
    readonly property color tint: stale ? '#71838c' : Model.ramp(cpu.idlePct)
    readonly property real pressure: cpu.psi && cpu.psi.some ? cpu.psi.some.avg10 : 0
    readonly property var rows: cpu.hogs || []
    onRowsChanged: page=Math.min(page,Math.max(0,Math.ceil(rows.length/8)-1))
    readonly property var cores: cpu.cores || []
    readonly property var coreLoads: cores.map(function(c){return c.busy})
    readonly property var chart: histories[String(range)] || {points:[],seconds:range,now:now,bucket:15,count:0,peak:0}
    readonly property string health: stale ? 'WAITING FOR TELEMETRY' : cpu.temp >= 90 ? 'RUNNING HOT' : pressure >= 10 ? 'CPU IS CONTENDED' : cpu.busyPct >= 85 ? 'FULLY LOADED' : 'CRUISING'
    readonly property real openPanelIndicatorWidth: button.width-12

    function setMode(value) {
        root.settings=Object.assign({}, root.settings, {displayMode:Model.clamp(value,0,3)})
        if(root.bar && root.bar.shell) root.bar.shell.updateEntryInline(root.moduleName,root.settings)
    }
    function runAction(action, extra) {
        if(actionProc.running) return
        actionStatus=action==='profile'?'Asking power-profiles-daemon…':'Finding the existing window…'
        actionProc.command=['python3',helper,action].concat(extra||[])
        actionProc.running=true
    }
    function status() {
        return JSON.stringify({opened:opened,mode:mode,readout:Model.readout(cpu,mode),tint:String(tint),stale:stale,samples:chart.count || 0,tab:tab,chooseMode:chooseMode,busy:cpu.busyPct,temp:cpu.temp,threads:cpu.threads,hogs:rows.length,profile:cpu.profile,action:actionStatus})
    }
    onOpenedChanged: if(opened) { snapshotFile.reload(); historyFile.reload() }
    FileView {
        id:snapshotFile; path:root.stateDir+'/snapshot.json'; watchChanges:true; printErrors:false
        onFileChanged:reload()
        onLoaded:{try{var m=JSON.parse(text());if(m.warm)root.cpu=m}catch(e){}}
    }
    FileView {
        id:historyFile; path:root.stateDir+'/history.json'; watchChanges:true; printErrors:false
        onFileChanged:reload()
        onLoaded:{try{root.histories=JSON.parse(text())}catch(e){}}
    }
    Timer { interval:3000; running:true; repeat:true; onTriggered:{root.now=Date.now()/1000; if(root.stale)snapshotFile.reload()} }
    Process {
        id:actionProc
        stdout:StdioCollector { onStreamFinished:{try{var r=JSON.parse(text);root.actionStatus=r.error || r.message || 'Done';if(!r.error && r.message && r.message.indexOf('Focused ')===0)root.close()}catch(e){root.actionStatus='Action could not complete.'}} }
        onExited:function(code){if(code!==0 && root.actionStatus.indexOf('…')>=0)root.actionStatus='Action could not complete.'}
    }
    IpcHandler {
        target:'nixfred.cpu-pulse'
        function open():void {root.chooseMode=false;root.open()}
        function close():void {root.close()}
        function toggle():void {root.chooseMode=false;root.toggle()}
        function status():string {return root.status()}
        function modes():void {root.chooseMode=true;root.open()}
        function display(value:int):void {root.setMode(value)}
        function showTab(value:int):void {root.tab=Model.clamp(value,0,2);root.chooseMode=false;root.open()}
        function historyRange(value:int):void {if([3600,86400,604800].indexOf(value)>=0)root.range=value}
    }
    WidgetButton {
        id:button; anchors.fill:parent;bar:root.bar;labelVisible:false;hasVisualContent:true
        fixedWidth:vertical?-1:barRow.implicitWidth+12
        tooltipText:'CPU Pulse · '+(root.stale?'Telemetry offline':Model.pct(root.cpu.busyPct)+' busy · '+Model.ghz(root.cpu.freq?root.cpu.freq.avg:null)+' · '+Model.temp(root.cpu.temp))+'\nLeft-click: dashboard · Right-click: readout'
        onPressed:function(b){if(b===Qt.RightButton){root.chooseMode=true;root.open()}else{root.chooseMode=false;root.toggle()}}
        Row {
            id:barRow;anchors.centerIn:parent;spacing:4
            CpuChip {compact:true;busy:root.cpu.busyPct || 0;cores:root.coreLoads;tint:root.tint;animate:!root.stale && root.setting('animated',true)}
            Column {
                anchors.verticalCenter:parent.verticalCenter
                Text {text:root.stale?'—':Model.readout(root.cpu,root.mode);color:root.barForeground;font.family:Style.font.family;font.pixelSize:12;font.bold:true}
                Text {text:Model.modeTag(root.mode);color:root.tint;font.pixelSize:7;font.letterSpacing:0.8}
            }
        }
    }
    component Label: Text {
        color:'#91a5b0';font.pixelSize:12;textFormat:Text.PlainText
    }
    component Heading: Text {
        color:'#eff7fa';font.pixelSize:15;font.bold:true;textFormat:Text.PlainText
    }
    component Action: Rectangle {
        id:act
        property string text:''
        property bool selected:false
        property color accent:root.tint
        signal clicked()
        implicitWidth:caption.implicitWidth+26;implicitHeight:34
        radius:9;color:act.selected?Qt.alpha(accent,0.18):area.containsMouse?'#22333f':'#14222b'
        border.color:act.selected?accent:area.containsMouse?'#536a76':'#2a3b47'
        Behavior on color {ColorAnimation{duration:120}}
        Text{id:caption;anchors.centerIn:parent;text:act.text;color:act.selected?'#ffffff':'#c3d3dc';font.pixelSize:12;font.bold:act.selected;textFormat:Text.PlainText}
        MouseArea{id:area;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor;onClicked:act.clicked()}
    }
    component Stat: Rectangle {
        property string label:''
        property string value:''
        property string hint:''
        radius:12;color:'#111e28';border.color:'#253744'
        Column {anchors.fill:parent;anchors.margins:12;spacing:5
            Label{text:label;font.pixelSize:10;font.letterSpacing:1}
            Heading{text:value;font.pixelSize:20}
            Label{text:hint;font.pixelSize:10}
        }
    }
    KeyboardPanel {
        id:panel;anchorItem:button;owner:root;bar:root.bar;open:root.opened;focusTarget:body
        contentWidth:panel.fittedContentWidth(root.chooseMode?370:740)
        contentHeight:panel.fittedContentHeight(root.chooseMode?modeColumn.implicitHeight:mainColumn.implicitHeight)
        Item {
            id:body;anchors.fill:parent;focus:true
            Keys.onEscapePressed:root.close()
            Keys.onPressed:function(event){
                if(event.key===Qt.Key_Left && !root.chooseMode){root.tab=Math.max(0,root.tab-1);event.accepted=true}
                if(event.key===Qt.Key_Right && !root.chooseMode){root.tab=Math.min(2,root.tab+1);event.accepted=true}
                if(root.chooseMode && event.key>=Qt.Key_1 && event.key<=Qt.Key_4){root.setMode(event.key-Qt.Key_1);event.accepted=true}
            }
            Rectangle {anchors.fill:parent;anchors.margins:-10;radius:14;color:'#0b141d'}
            Column {
                id:modeColumn;width:parent.width;spacing:12;visible:root.chooseMode
                Heading{text:'BAR READOUT';font.letterSpacing:1.5}
                Label{text:'Choose what lives beside the die. One decimal.'}
                Repeater {
                    model:4
                    Action {
                        required property int index
                        width:modeColumn.width;height:44;selected:root.mode===index
                        text:(index+1)+'.  '+Model.modeName(index)+'   ·   '+Model.readout(root.cpu,index)
                        onClicked:root.setMode(index)
                    }
                }
                Action{text:'Open processor dashboard →';width:parent.width;onClicked:root.chooseMode=false}
            }
            Column {
                id:mainColumn;width:parent.width;spacing:14;visible:!root.chooseMode
                Row {
                    width:parent.width;spacing:10
                    Column {width:parent.width-220;spacing:3
                        Heading{text:'CPU PULSE';font.pixelSize:19;font.letterSpacing:3}
                        Label{text:'Your processor, in motion.';font.pixelSize:11}
                    }
                    Rectangle {width:190;height:32;radius:16;color:Qt.alpha(root.tint,0.14);border.color:Qt.alpha(root.tint,0.5)
                        Row {anchors.centerIn:parent;spacing:7
                            Rectangle {width:6;height:6;radius:3;color:root.tint;anchors.verticalCenter:parent.verticalCenter
                                SequentialAnimation on opacity {running:root.opened&&!root.stale;loops:Animation.Infinite;NumberAnimation{to:0.3;duration:900}NumberAnimation{to:1;duration:900}}
                            }
                            Label{text:root.health;color:'#e4edf0';font.pixelSize:9;font.bold:true}
                        }
                    }
                }
                Row {spacing:8
                    Repeater {model:['Overview','CPU hogs','Processor lab']
                        Action {required property int index;required property string modelData;text:modelData;selected:root.tab===index;onClicked:root.tab=index}
                    }
                }
                Column {
                    width:parent.width;spacing:14;visible:root.tab===0
                    height:visible?implicitHeight:0
                    Rectangle {
                        width:parent.width;height:170;radius:16;border.color:Qt.alpha(root.tint,0.45)
                        gradient:Gradient {GradientStop{position:0;color:Qt.alpha(root.tint,0.13)}GradientStop{position:1;color:'#111d27'}}
                        CpuChip {id:heroChip;x:12;y:5;width:160;height:160;busy:root.cpu.busyPct || 0;cores:root.coreLoads;tint:root.tint;animate:root.opened&&root.tab===0&&!root.stale&&root.setting('animated',true)}
                        Column {x:188;y:20;spacing:6
                            Label{text:'PROCESSOR BUSY';font.pixelSize:11;font.letterSpacing:2}
                            Row {spacing:10
                                Text {text:root.stale?'—':(root.cpu.busyPct||0).toFixed(1);color:'#f4fafc';font.pixelSize:52;font.weight:Font.Light}
                                Label{text:'%';font.pixelSize:18;anchors.bottom:parent.bottom;anchors.bottomMargin:10}
                            }
                            Label{text:Model.ghz(root.cpu.freq?root.cpu.freq.avg:null)+' average clock  /  '+(root.cpu.threads||0)+' threads on '+(root.cpu.physical||0)+' cores';color:'#c4d6dc'}
                            Label{text:(root.cpu.model||'Unknown processor')+'  ·  busy = everything except idle and I/O wait';font.pixelSize:10;width:520;elide:Text.ElideRight}
                        }
                        Text {anchors.right:parent.right;anchors.rightMargin:20;anchors.top:parent.top;anchors.topMargin:22;text:Model.temp(root.cpu.temp)+'\npackage';color:Qt.alpha('#edf7fa',0.5);font.pixelSize:15;horizontalAlignment:Text.AlignRight}
                    }
                    Row {width:parent.width;spacing:10
                        Stat{width:(parent.width-20)/3;height:96;label:'LOAD · 1 MIN';value:Model.load((root.cpu.load||[0])[0]);hint:Model.pct(root.cpu.loadPct)+' of '+(root.cpu.threads||0)+' threads · 5m '+Model.load((root.cpu.load||[0,0])[1])+' · 15m '+Model.load((root.cpu.load||[0,0,0])[2])}
                        Stat{width:(parent.width-20)/3;height:96;label:'CLOCK';value:Model.ghz(root.cpu.freq?root.cpu.freq.avg:null);hint:'Fastest thread '+Model.ghz(root.cpu.freq?root.cpu.freq.peak:null)+' · ceiling '+Model.ghz(root.cpu.freq?root.cpu.freq.max:null)}
                        Stat{width:(parent.width-20)/3;height:96;label:'CPU PRESSURE';value:Model.pct(root.pressure);hint:'Time tasks waited for a CPU · last 10s'}
                    }
                    Rectangle {width:parent.width;height:242;radius:14;color:'#101c26';border.color:'#273843'
                        Column {anchors.fill:parent;anchors.margins:14;spacing:9
                            Row {width:parent.width;spacing:7
                                Heading{text:'CONTINUOUS HISTORY';font.pixelSize:12;width:parent.width-222;anchors.verticalCenter:parent.verticalCenter}
                                Repeater{model:[{t:'1 hour',s:3600},{t:'24 hours',s:86400},{t:'7 days',s:604800}]
                                    Action{required property var modelData;text:modelData.t;selected:root.range===modelData.s;implicitWidth:68;implicitHeight:28;onClicked:root.range=modelData.s}
                                }
                            }
                            HistoryGraph{width:parent.width;height:139;historyData:root.chart;tint:root.tint}
                            Row{spacing:14
                                Label{text:'━ CPU busy';color:root.tint;font.pixelSize:10}
                                Label{text:'━ Package °C';color:'#ffa86b';font.pixelSize:10}
                                Label{text:'Peak '+Model.pct(root.chart.peak)+'  ·  '+(root.chart.count||0)+' samples';font.pixelSize:10}
                            }
                            Label{text:(root.chart.count||0)<2?'History is starting. Samples accumulate every 15 seconds.':'Recording while closed · 7-day retention · hover to inspect · faint line = busy peaks';font.pixelSize:10}
                        }
                    }
                    Rectangle {width:parent.width;height:coreColumn.implicitHeight+28;radius:14;color:'#121b2c';border.color:'#303a57'
                        Column{id:coreColumn;anchors.fill:parent;anchors.margins:14;spacing:9
                            Row{width:parent.width
                                Heading{text:'EVERY THREAD';font.pixelSize:12;width:parent.width/2}
                                Label{text:root.cores.filter(function(c){return c.busy>=50}).length+' of '+root.cores.length+' above half load';width:parent.width/2;horizontalAlignment:Text.AlignRight;color:'#c0c8ff'}
                            }
                            Grid{width:parent.width;columns:Math.max(1,Math.min(6,root.cores.length));columnSpacing:8;rowSpacing:8
                                Repeater{model:root.cores
                                    Column{required property var modelData;width:(coreColumn.width-8*5)/6;spacing:4
                                        Row{width:parent.width
                                            Label{text:'T'+modelData.id;font.pixelSize:10;color:'#c0c8ff';width:parent.width/2}
                                            Label{text:Model.pct(modelData.busy);font.pixelSize:10;width:parent.width/2;horizontalAlignment:Text.AlignRight;color:'#e4edf0'}
                                        }
                                        Rectangle{width:parent.width;height:5;radius:3;color:'#273148'
                                            Rectangle{width:parent.width*Model.clamp(modelData.busy/100,0,1);height:parent.height;radius:3;color:Model.ramp(100-modelData.busy);Behavior on width{NumberAnimation{duration:800}}}
                                        }
                                        Label{text:Model.ghz(modelData.freq)+(modelData.temp!==null&&modelData.temp!==undefined?' · '+Model.temp(modelData.temp):'');font.pixelSize:9}
                                    }
                                }
                            }
                            Label{text:'Sibling threads share a physical core; the clock is the average delivered frequency, idle time included.';font.pixelSize:10}
                        }
                    }
                }
                Column {
                    width:parent.width;spacing:10;visible:root.tab===1;height:visible?implicitHeight:0
                    Row{width:parent.width
                        Heading{text:'TOP CPU HOGS';width:parent.width-210;font.pixelSize:13}
                        Label{text:'Ranked by CPU time · refresh 9s';font.pixelSize:10}
                    }
                    Label{text:'Click a row to visit its app or attached session. Background processes show details.';font.pixelSize:11}
                    Repeater {
                        model:root.rows.slice(root.page*8,root.page*8+8)
                        Rectangle {
                            id:procRow
                            required property var modelData
                            required property int index
                            width:mainColumn.width;height:65;radius:10
                            color:hogMouse.containsMouse?'#1d303b':'#111e28';border.color:hogMouse.containsMouse?root.tint:'#263844'
                            Rectangle{anchors.left:parent.left;anchors.bottom:parent.bottom;anchors.leftMargin:12;anchors.bottomMargin:5;width:(parent.width-24)*Model.clamp(procRow.modelData.cpu/(100*(root.cpu.threads||1)),0,1);height:2;radius:1;color:root.tint}
                            Label{x:12;y:22;text:String(root.page*8+procRow.index+1).padStart(2,'0');font.pixelSize:12;color:root.tint}
                            Column{x:44;y:10;spacing:5;width:parent.width-222
                                Heading{text:procRow.modelData.name+'  ·  '+procRow.modelData.pid;font.pixelSize:13;width:parent.width;elide:Text.ElideRight}
                                Label{text:procRow.modelData.target.address?(procRow.modelData.target.host.kind==='herdr'?'Herdr '+procRow.modelData.target.host.pane+' · ':procRow.modelData.target.host.kind==='tmux'?'tmux '+procRow.modelData.target.host.pane+' · ':'')+procRow.modelData.target.title:'Background process · no attached window';width:parent.width;elide:Text.ElideRight;font.pixelSize:10}
                            }
                            Column{anchors.right:parent.right;anchors.rightMargin:35;y:10;spacing:5
                                Heading{text:Model.pct(procRow.modelData.cpu);font.pixelSize:15;anchors.right:parent.right}
                                Label{text:(procRow.modelData.sampled?'':'lifetime avg · ')+procRow.modelData.threads+' threads';font.pixelSize:10;anchors.right:parent.right}
                            }
                            Label{anchors.right:parent.right;anchors.rightMargin:13;y:22;text:procRow.modelData.target.address?'↗':'ⓘ';color:root.tint;font.pixelSize:16}
                            MouseArea{id:hogMouse;anchors.fill:parent;hoverEnabled:true;cursorShape:Qt.PointingHandCursor
                                onClicked: {if(procRow.modelData.target.address)root.runAction('focus',[String(procRow.modelData.pid),String(procRow.modelData.start)]);else root.actionStatus=procRow.modelData.name+' · PID '+procRow.modelData.pid+' · '+Model.pct(procRow.modelData.cpu/(root.cpu.threads||1))+' of the whole processor · nice '+procRow.modelData.nice+' · state '+procRow.modelData.state+'. No existing window to focus.'}
                            }
                        }
                    }
                    Row{spacing:10
                        Action{text:'← Previous';opacity:root.page>0?1:0.4;onClicked:root.page=Math.max(0,root.page-1)}
                        Label{text:(root.page+1)+' / '+Math.max(1,Math.ceil(root.rows.length/8));anchors.verticalCenter:parent.verticalCenter}
                        Action{text:'Next →';opacity:(root.page+1)*8<root.rows.length?1:0.4;onClicked:root.page=Math.min(Math.max(0,Math.ceil(root.rows.length/8)-1),root.page+1)}
                    }
                    Label{width:parent.width;wrapMode:Text.WordWrap;text:'Percentages are of one thread, like top: a process can exceed 100%. The bar under each row is its share of the whole processor. Browser subprocesses lead to their browser window.';font.pixelSize:10}
                }
                Column {
                    width:parent.width;spacing:12;visible:root.tab===2;height:visible?implicitHeight:0
                    Heading{text:'UNDER THE HOOD';font.pixelSize:13}
                    Grid{width:parent.width;columns:3;spacing:10
                        Repeater{model:[
                            {l:'USER',v:Model.pct((root.cpu.breakdown||{}).user),h:'Time in application code'},
                            {l:'SYSTEM',v:Model.pct((root.cpu.breakdown||{}).system),h:'Time inside the kernel'},
                            {l:'NICE',v:Model.pct((root.cpu.breakdown||{}).nice),h:'Low-priority background work'},
                            {l:'I/O WAIT',v:Model.pct((root.cpu.breakdown||{}).iowait),h:'Idle while storage catches up'},
                            {l:'IRQ + SOFTIRQ',v:Model.pct(((root.cpu.breakdown||{}).irq||0)+((root.cpu.breakdown||{}).softirq||0)),h:'Interrupt handling · network, timers'},
                            {l:'STEAL',v:Model.pct((root.cpu.breakdown||{}).steal),h:'Taken by a hypervisor · 0 on bare metal'},
                            {l:'CONTEXT SWITCHES',v:Model.rate((root.cpu.rates||{}).ctxt),h:'Task changes per second'},
                            {l:'INTERRUPTS',v:Model.rate((root.cpu.rates||{}).intr),h:'Hardware and timer interrupts'},
                            {l:'NEW PROCESSES',v:Model.rate((root.cpu.rates||{}).processes),h:'Forks and clones per second'},
                            {l:'RUNNABLE NOW',v:String(root.cpu.running||0),h:'Tasks running or queued this instant'},
                            {l:'BLOCKED ON I/O',v:String(root.cpu.blocked||0),h:'Tasks in uninterruptible sleep'},
                            {l:'ALL TASKS STALLED',v:Model.pct(root.cpu.psi&&root.cpu.psi.full?root.cpu.psi.full.avg10:0),h:'Full CPU pressure · last 10s'}
                        ]
                            Stat{required property var modelData;width:(mainColumn.width-20)/3;height:91;label:modelData.l;value:modelData.v;hint:modelData.h}
                        }
                    }
                    Column{width:parent.width;spacing:7
                        Label{width:parent.width;text:(root.cpu.freq?root.cpu.freq.driver+' · '+root.cpu.freq.governor+' governor'+(root.cpu.freq.epp?' · '+root.cpu.freq.epp+' preference':'')+' · turbo '+(root.cpu.freq.turbo===true?'on':root.cpu.freq.turbo===false?'off':'unknown')+' · base '+Model.ghz(root.cpu.freq.base):'Frequency driver unavailable')+'  ·  throttled '+((root.cpu.throttle||{}).package||0)+'× since boot'+(root.cpu.watts!==null&&root.cpu.watts!==undefined?'  ·  '+root.cpu.watts.toFixed(1)+' W package':'');color:'#b6c0fb';font.pixelSize:11;wrapMode:Text.WordWrap}
                        Label{width:parent.width;text:(root.cpu.sensors||[]).map(function(s){return s.label+' '+Model.temp(s.temp)}).join('  ·  ') || 'No CPU temperature sensors exposed';color:'#b6c0fb';font.pixelSize:11;wrapMode:Text.WordWrap}
                    }
                    Rectangle{width:parent.width;height:152;radius:12;color:'#11251f';border.color:'#2c5547'
                        Column{anchors.fill:parent;anchors.margins:14;spacing:9
                            Heading{text:'POWER PROFILE';font.pixelSize:12}
                            Label{width:parent.width;wrapMode:Text.WordWrap;text:root.cpu.profile?'power-profiles-daemon shapes clocks and thermals for the whole machine. Changes apply immediately and are fully reversible here. Performance costs battery and heat; power-saver costs responsiveness.':'power-profiles-daemon is not running, so profiles cannot be switched from here.';font.pixelSize:11;color:'#abc4b9'}
                            Row{spacing:8
                                Repeater{model:['power-saver','balanced','performance']
                                    Action{required property string modelData;text:actionProc.running&&root.actionStatus.indexOf('Asking')===0?'Working…':modelData;accent:'#63c89e';selected:root.cpu.profile===modelData;opacity:root.cpu.profile?1:0.4;onClicked:if(root.cpu.profile)root.runAction('profile',[modelData])}
                                }
                            }
                        }
                    }
                    Label{width:parent.width;wrapMode:Text.WordWrap;text:'Breakdown fields sum to 100% of processor time. No process termination, renicing, affinity pinning, frequency locking or privileged tuning is exposed.';font.pixelSize:10}
                }
                Rectangle{width:parent.width;height:1;color:'#25343f'}
                Label{width:parent.width;wrapMode:Text.WordWrap;font.pixelSize:10;color:root.stale?'#f0ba82':'#a4b9c3';text:root.actionStatus || (root.stale?'Telemetry is offline. Check the cpu-pulse user service.': 'LIVE · updated '+Qt.formatTime(new Date(root.cpu.ts*1000),'h:mm:ss AP')+'  ·  History stays on this machine  ·  Esc closes')}
            }
        }
    }
}
