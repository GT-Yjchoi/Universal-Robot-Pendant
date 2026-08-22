import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property int speed: 1
    property var valves: []
    signal closeRequested()
    signal axisChanged(string name, bool active)
    signal speedSelected(int speed)
    signal valveChanged(int index, bool active)
    width: 300; color: "#f5080c15"; radius: 14; border.color: "#00e5ff"; border.width: 2
    ColumnLayout {
        anchors.fill:parent; anchors.margins:14; spacing:8
        RowLayout { Layout.fillWidth:true
            Text { Layout.fillWidth:true; text:"JOG CONTROL"; color:"#00e5ff"; font.pixelSize:20; font.bold:true }
            PendantButton { Layout.preferredWidth:50; text:"✕"; accent:"#777777"; onClicked:root.closeRequested() }
        }
        Rectangle { Layout.fillWidth:true; height:2; color:"#00e5ff" }
        GridLayout {
            columns:2; Layout.fillWidth:true; rowSpacing:8; columnSpacing:8
            Repeater { model:["X -","X +","Y -","Y +","Z -","Z +","A -","A +"]
                PendantButton { required property string modelData; Layout.fillWidth:true; Layout.preferredHeight:58; text:modelData; accent:"#007f91"; onPressed:root.axisChanged(modelData,true); onReleased:root.axisChanged(modelData,false) }
            }
        }
        Text { Layout.alignment:Qt.AlignHCenter; text:"JOG SPEED"; color:"#aaaaaa"; font.pixelSize:13 }
        RowLayout { Layout.fillWidth:true; spacing:5
            Repeater { model:5
                PendantButton { required property int index; Layout.fillWidth:true; text:String(index+1); accent:root.speed===index+1?"#00e5ff":"#555d66"; textColor:root.speed===index+1?"#00e5ff":"#aaaaaa"; onClicked:root.speedSelected(index+1) }
            }
        }
        Text { visible:root.valves.length>0; Layout.alignment:Qt.AlignHCenter; text:"VALVE"; color:"#aaaaaa"; font.pixelSize:13 }
        GridLayout {
            columns:2; Layout.fillWidth:true; rowSpacing:6; columnSpacing:6
            Repeater { model:root.valves
                PendantButton {
                    required property var modelData; Layout.fillWidth:true; Layout.preferredHeight:52
                    text:modelData.name; checkable:modelData.mode==="toggle"; checked:modelData.on
                    accent:modelData.on?"#ff9900":"#007f91"
                    onClicked:if(modelData.mode==="toggle") root.valveChanged(modelData.index,checked)
                    onPressed:if(modelData.mode!=="toggle") root.valveChanged(modelData.index,true)
                    onReleased:if(modelData.mode!=="toggle") root.valveChanged(modelData.index,false)
                }
            }
        }
        Item { Layout.fillHeight:true }
    }
}
