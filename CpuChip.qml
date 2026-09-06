import QtQuick
import "Model.js" as Model

// A glowing processor die. Each core is a cell that brightens with load; a
// clock beam sweeps the die while telemetry is live. The aura, orbit rings and
// pins match RAM Pulse so the two chips read as siblings on the bar.
Item {
    id: root
    property real busy: 0
    property var cores: []
    property bool animate: true
    property bool compact: false
    property color tint: Model.ramp(100 - busy)
    property real phase: 0
    property real level: busy / 100
    property var shown: []
    implicitWidth: compact ? 28 : 160
    implicitHeight: compact ? 25 : 160
    Behavior on level { NumberAnimation { duration: 1200; easing.type: Easing.InOutCubic } }
    Behavior on tint { ColorAnimation { duration: 1100 } }
    NumberAnimation on phase { from: 0; to: 1; duration: 5800; loops: Animation.Infinite; running: root.animate }
    onPhaseChanged: canvas.requestPaint()
    onTintChanged: canvas.requestPaint()
    onLevelChanged: canvas.requestPaint()
    onCoresChanged: canvas.requestPaint()
    Canvas {
        id: canvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext('2d'), w = width, h = height
            c.reset(); c.clearRect(0,0,w,h)
            var cx=w/2, cy=h/2, size=Math.min(w,h), body=size*(root.compact?0.58:0.47)
            var x=cx-body/2, y=cy-body/2, t=root.phase*Math.PI*2
            var aura=c.createRadialGradient(cx,cy,body*0.1,cx,cy,size*0.5)
            aura.addColorStop(0,Qt.alpha(root.tint,0.30+0.25*root.level)); aura.addColorStop(0.6,Qt.alpha(root.tint,0.20+0.07*Math.sin(t))); aura.addColorStop(1,'transparent')
            c.fillStyle=aura; c.fillRect(0,0,w,h)
            if (!root.compact) {
                for(var ring=0;ring<3;ring++) {
                    c.beginPath(); c.strokeStyle=Qt.alpha(root.tint,0.11+ring*0.04); c.lineWidth=1
                    c.arc(cx,cy,body*(0.78+ring*0.12),0,Math.PI*2); c.stroke()
                    c.beginPath(); c.strokeStyle=Qt.alpha(root.tint,0.65); c.lineWidth=2
                    var ang=t*(ring%2===0?1:-1)*(1+root.level)+ring*2
                    c.arc(cx,cy,body*(0.78+ring*0.12),ang,ang+0.42);c.stroke()
                }
            }
            c.fillStyle='#0b141b'; c.strokeStyle=root.tint; c.lineWidth=root.compact?1.2:2
            c.fillRect(x,y,body,body)
            c.shadowColor=root.tint; c.shadowBlur=root.compact?5:12
            c.strokeRect(x,y,body,body); c.shadowBlur=0
            c.save();c.beginPath();c.rect(x+2,y+2,body-4,body-4);c.clip()
            // Core grid. Values ease toward the latest sample on every frame so a
            // burst lights up without a hard cut.
            var values=root.cores && root.cores.length?root.cores:[root.busy]
            var n=values.length, cols=Math.ceil(Math.sqrt(n)), rows=Math.ceil(n/cols)
            if(root.shown.length!==n) root.shown=values.map(function(v){return Model.clamp(v,0,100)/100})
            var gap=root.compact?1:3, inner=body-4, cw=(inner-gap*(cols+1))/cols, ch=(inner-gap*(rows+1))/rows
            for(var i=0;i<n;i++){
                var target=Model.clamp(values[i],0,100)/100
                root.shown[i]=root.animate?root.shown[i]+(target-root.shown[i])*0.12:target
                var v=Model.clamp(root.shown[i],0,1), col=i%cols, row=Math.floor(i/cols)
                var px=x+2+gap+col*(cw+gap), py=y+2+gap+row*(ch+gap)
                c.fillStyle=Qt.alpha(root.tint,0.10+0.80*v)
                c.fillRect(px,py,cw,ch)
                if(!root.compact && v>0.5){
                    c.fillStyle=Qt.alpha('#ffffff',(v-0.5)*0.5)
                    c.fillRect(px+cw*0.3,py+ch*0.3,cw*0.4,ch*0.4)
                }
            }
            // Clock beam: sweeps the die at a pace that quickens with load.
            var sweep=((root.phase*(1+root.level*2))%1)*(body+16)-8
            var beam=c.createLinearGradient(x+sweep-8,0,x+sweep+8,0)
            beam.addColorStop(0,'transparent'); beam.addColorStop(0.5,Qt.alpha('#ffffff',root.compact?0.28:0.36)); beam.addColorStop(1,'transparent')
            c.fillStyle=beam; c.fillRect(x+sweep-8,y,16,body)
            c.strokeStyle=Qt.alpha(root.tint,0.35);c.lineWidth=0.8
            for(var line=1;line<4;line++){ c.beginPath();c.moveTo(x,y+body*line/4);c.lineTo(x+body,y+body*line/4);c.stroke() }
            c.restore()
            c.strokeStyle=root.tint;c.lineWidth=root.compact?1:2
            for(var pin=0;pin<4;pin++) {
                var p=body*(pin+1)/5, len=body*0.17
                c.beginPath();c.moveTo(x+p,y-len);c.lineTo(x+p,y);c.moveTo(x+p,y+body);c.lineTo(x+p,y+body+len)
                c.moveTo(x-len,y+p);c.lineTo(x,y+p);c.moveTo(x+body,y+p);c.lineTo(x+body+len,y+p);c.stroke()
                if(!root.compact){
                    var progress=(root.phase*(1+root.level)+pin/4)%1
                    c.fillStyle=Qt.alpha(root.tint,1-progress*0.5)
                    c.beginPath();c.arc(x+p,y+body+len+progress*body*0.3,1.7,0,Math.PI*2);c.fill()
                    c.beginPath();c.arc(x-len-progress*body*0.3,y+p,1.7,0,Math.PI*2);c.fill()
                }
            }
        }
    }
}
