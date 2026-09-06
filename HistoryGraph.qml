import QtQuick
import "Model.js" as Model

Item {
    id: root
    property var historyData: ({points:[], seconds:3600, now:0, bucket:15})
    property color tint: '#43f2a1'
    property color heat: '#ffa86b'
    property int hoverIndex: -1
    readonly property var points: historyData.points || []
    readonly property var hoverPoint: points[hoverIndex] || null
    onHistoryDataChanged: { hoverIndex=-1; graph.requestPaint() }
    onTintChanged: graph.requestPaint()
    Canvas {
        id: graph
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c=getContext('2d'), w=width-38, h=height-26
            c.reset();c.clearRect(0,0,width,height)
            c.font='10px sans-serif';c.textAlign='right'
            for(var line=0;line<=4;line++){
                var y=8+(h-8)*line/4
                c.strokeStyle='#233039';c.lineWidth=1;c.beginPath();c.moveTo(0,y);c.lineTo(w,y);c.stroke()
                c.fillStyle='#7e959f';c.fillText(String(100-line*25),width,y+3)
            }
            function xAt(p){return w*(p[0]-(root.historyData.now-root.historyData.seconds))/root.historyData.seconds}
            function yAt(v){return 8+(h-8)*(1-Model.clamp(v,0,100)/100)}
            var pts=root.points
            // Empty elapsed time stays empty. Gaps and reboots break every trace.
            // Column 1 is average busy, 2 the bucket peak, 3 the package temperature.
            for(var metric=1;metric<=3;metric++){
                c.lineWidth=metric===1?2.2:1
                c.strokeStyle=metric===3?root.heat:metric===2?Qt.alpha(root.tint,0.28):root.tint
                c.beginPath()
                for(var i=0;i<pts.length;i++){
                    var p=pts[i], x=xAt(p), y=yAt(p[metric])
                    if(metric===3 && !(p[3]>0)) { continue }
                    if(i===0 || p[0]-pts[i-1][0]>root.historyData.bucket*2.5 || p[6]!==pts[i-1][6] || (metric===3 && !(pts[i-1][3]>0))) c.moveTo(x,y)
                    else c.lineTo(x,y)
                }
                c.stroke()
            }
            if(pts.length){
                var last=pts[pts.length-1]
                c.fillStyle=root.tint;c.beginPath();c.arc(xAt(last),yAt(last[1]),3,0,Math.PI*2);c.fill()
            }
            c.fillStyle='#7e959f';c.textAlign='left';c.fillText(root.historyData.seconds===3600?'1 hour ago':root.historyData.seconds===86400?'24 hours ago':'7 days ago',0,height-3)
            c.textAlign='right';c.fillText('now',w,height-3)
        }
    }
    Rectangle {
        visible: root.hoverPoint !== null
        x: root.hoverPoint ? Math.max(0,Math.min(parent.width-38,(root.hoverPoint[0]-(root.historyData.now-root.historyData.seconds))/root.historyData.seconds*(parent.width-38))) : 0
        y: 8; width: 1; height: parent.height-34; color: '#71878f'
    }
    Rectangle {
        visible: root.hoverPoint !== null
        anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter
        width: hoverText.implicitWidth+20; height: 27; radius: 7; color:'#17232d';border.color:'#40525f'
        Text {
            id: hoverText; anchors.centerIn:parent; color:'#edf5f7';font.pixelSize:11
            text: {
                var p=root.hoverPoint
                if(!p) return ''
                return Qt.formatDateTime(new Date(p[0]*1000),'ddd h:mm AP')+'  ·  CPU '+Model.pct(p[1])+'  ·  peak '+Model.pct(p[2])+'  ·  '+(p[3]>0?Model.temp(p[3]):'no temp')
            }
        }
    }
    MouseArea {
        anchors.fill:parent; hoverEnabled:true; acceptedButtons:Qt.NoButton
        onExited:root.hoverIndex=-1
        onPositionChanged:function(mouse){
            var wanted=root.historyData.now-root.historyData.seconds+mouse.x/(width-38)*root.historyData.seconds, best=-1, distance=Infinity
            for(var i=0;i<root.points.length;i++){var d=Math.abs(root.points[i][0]-wanted);if(d<distance){distance=d;best=i}}
            root.hoverIndex=distance<root.historyData.bucket*3?best:-1
        }
    }
}
