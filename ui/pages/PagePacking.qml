import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../qml/components" as Components

Rectangle {
    id: root
    color: "#111821"
    property var editAxis: ({})
    property string editField: ""

    component GlassPanel: Rectangle {
        color: "#171f2a"; radius: 12
        border.color: "#34404f"; border.width: 1
    }
    component ActionButton: Button {
        id: control
        implicitHeight: 46
        font.pixelSize: 16; font.bold: true
        contentItem: Text { text: control.text; color: control.palette.buttonText; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; font: control.font }
        background: Rectangle { radius: 8; color: control.down ? "#3b4e64" : "#263545"; border.color: "#536b82" }
    }

    RowLayout {
        anchors.fill: parent; anchors.margins: 8; spacing: 14
        GlassPanel {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 4
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 8
                Text { Layout.alignment: Qt.AlignHCenter; text: "파렛타이징 시뮬레이션"; color: "#eeeeee"; font.pixelSize: 18; font.bold: true }
                Text { Layout.fillWidth: true; text: packingBackend ? packingBackend.baseText : ""; color: text.startsWith("⚠") ? "#ffb060" : "#64ffda"; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; font.pixelSize: 13 }
                RowLayout {
                    Layout.fillWidth: true
                    ActionButton { Layout.fillWidth: true; text: packingBackend ? packingBackend.orderText : ""; palette.buttonText: "#80b8ff"; onClicked: if (packingBackend) packingBackend.cycleOrder() }
                    ActionButton { Layout.fillWidth: true; text: packingBackend && packingBackend.playing ? "정지" : "실행"; palette.buttonText: packingBackend && packingBackend.playing ? "#ff7070" : "#64ff9a"; onClicked: if (packingBackend) packingBackend.toggleSimulation() }
                }
                Canvas {
                    id: pallet
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Connections { target: packingBackend; function onAnimationChanged() { pallet.requestPaint() } function onChanged() { pallet.requestPaint() } }
                    onPaint: {
                        var c=getContext("2d"); c.reset(); c.fillStyle="#1e2631"; c.fillRect(0,0,width,height)
                        if (!packingBackend) return
                        var axes=packingBackend.axes, xc=axes[0].count, yc=axes[1].count, zc=axes[2].count
                        var a=packingBackend.anim, margin=15, zw=30, zx=width-margin-zw, zy=35, zh=height-zy-margin
                        c.fillStyle="#343c48"; c.fillRect(zx,zy,zw,zh)
                        var dz=packingBackend.simState===2 ? zc : Math.min(zc,a[2]+1)
                        c.fillStyle=packingBackend.simState===2 ? "#64ff64" : "#ffd280"; c.fillRect(zx,zy+zh-(zh/zc*dz),zw,zh/zc*dz)
                        c.fillStyle="#ddd"; c.font="bold 13px sans-serif"; c.textAlign="center"; c.fillText("Z",zx+zw/2,23)
                        var gw=zx-margin*2, my=15, mh=40; c.fillStyle="#3c4652"; c.fillRect(margin,my,gw,mh)
                        c.fillStyle="#ffd280"; c.fillText("사출기",margin+gw/2,my+26)
                        var sy=my+mh+10, gh=height-sy-margin, cw=gw/yc, ch=gh/xc
                        var tr=axes[0].direction>0?a[0]:xc-1-a[0], tc=axes[1].direction>0?yc-1-a[1]:a[1]
                        for(var r=0;r<xc;r++) for(var col=0;col<yc;col++) {
                            var head=r===tr&&col===tc&&packingBackend.simState!==2
                            c.fillStyle=head?"#e8d5a9":(packingBackend.simState===2?"#3c424c":"#28313d")
                            c.fillRect(margin+col*cw+2,sy+r*ch+2,cw-4,ch-4)
                            c.fillStyle=head?"#111":"#777"; c.font="bold 10px sans-serif"; c.fillText(head?"HEAD":(r+1)+","+(col+1),margin+col*cw+cw/2,sy+r*ch+ch/2+4)
                        }
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 6; spacing: 10
            ActionButton {
                Layout.fillWidth: true; implicitHeight: 64
                text: packingBackend && packingBackend.enabled ? "● 패킹 사용" : "○ 패킹 미사용"
                palette.buttonText: packingBackend && packingBackend.enabled ? "#00ff7f" : "#999999"
                onClicked: if (packingBackend) packingBackend.setEnabled(!packingBackend.enabled)
            }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 10
                Repeater {
                    model: packingBackend ? packingBackend.axes : []
                    GlassPanel {
                        required property var modelData
                        Layout.fillWidth: true; Layout.fillHeight: true
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 10; spacing: 8
                            Text { Layout.alignment: Qt.AlignHCenter; text: modelData.axis+" 축 설정"; color: "white"; font.pixelSize: 18; font.bold: true }
                            Rectangle { Layout.fillWidth: true; height: 1; color: "#46515f" }
                            Text { text: "현재위치 (No.)"; color: "#aaa"; font.pixelSize: 13 }
                            ActionButton { Layout.fillWidth: true; text: String(modelData.current); palette.buttonText: modelData.color; onClicked: { root.editAxis=modelData; root.editField="current"; inputPopup.openWith(modelData.current,false) } }
                            Text { text: "설정횟수 (EA)"; color: "#aaa"; font.pixelSize: 13 }
                            ActionButton { Layout.fillWidth: true; text: String(modelData.count); palette.buttonText: "white"; onClicked: { root.editAxis=modelData; root.editField="count"; inputPopup.openWith(modelData.count,false) } }
                            Text { text: "설정피치 (mm)"; color: "#aaa"; font.pixelSize: 13 }
                            ActionButton { Layout.fillWidth: true; text: Number(modelData.pitch).toFixed(2); palette.buttonText: "white"; onClicked: { root.editAxis=modelData; root.editField="pitch"; inputPopup.openWith(modelData.pitch,true) } }
                            Text { text: "진행 방향"; color: "#aaa"; font.pixelSize: 13 }
                            ActionButton { Layout.fillWidth: true; text: modelData.direction>0 ? "+ 방향" : "- 방향"; palette.buttonText: modelData.direction>0?"#00e5ff":"#ff6060"; onClicked: packingBackend.toggleDirection(modelData.key) }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }
    }

    Components.NumberPadPopup {
        id: inputPopup
        title: root.editAxis.axis+" "+(root.editField==="pitch"?"피치":root.editField==="count"?"횟수":"현재위치")
        minimum: root.editField === "pitch" ? 0 : 1
        function openWith(value, isDecimal) { decimal=isDecimal; openValue(value) }
        onAccepted: function(value) {
            if (!packingBackend) return
            if(root.editField==="current") packingBackend.setCurrentIndex(root.editAxis.key,value)
            else packingBackend.setAxisValue(root.editAxis.key,root.editField,value)
        }
    }
}
