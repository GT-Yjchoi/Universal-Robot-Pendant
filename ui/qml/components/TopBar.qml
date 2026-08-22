import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property bool connected: false
    property string recipeName: "No Data"
    property string modeText: "모드: 정지"
    property color modeColor: "#95a5a6"
    property string alarmText: ""
    signal jogRequested()
    signal alarmRequested()
    color: "#18212c"; radius: 10; border.color: "#344353"; implicitHeight: 68
    RowLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 14
        Text { text: "UNIVERSAL PENDANT"; color: "#f0f4f8"; font.pixelSize: 20; font.bold: true }
        Rectangle { width:12; height:12; radius:6; color:root.connected?"#42e878":"#ff5252" }
        Text { text:root.connected?"PLC CONNECTED":"PLC OFFLINE"; color:root.connected?"#72f29a":"#ff7777"; font.pixelSize:14; font.bold:true }
        Text { text:root.modeText; color:root.modeColor; font.pixelSize:16; font.bold:true }
        Item { Layout.fillWidth:true }
        Text { text:root.recipeName; color:"#ffd280"; font.pixelSize:16; font.bold:true }
        PendantButton { visible:root.alarmText!==""; text:root.alarmText; accent:"#d9534f"; onClicked:root.alarmRequested() }
        PendantButton { text:"JOG"; accent:"#468cff"; Layout.preferredWidth:90; onClicked:root.jogRequested() }
        Text { id:clock; color:"#dce5ee"; font.pixelSize:17; font.bold:true
            function update(){ text=Qt.formatDateTime(new Date(),"yyyy-MM-dd  hh:mm:ss") }
            Component.onCompleted:update(); Timer{ interval:1000; running:true; repeat:true; onTriggered:clock.update() }
        }
    }
}
