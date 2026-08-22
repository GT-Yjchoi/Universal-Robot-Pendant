import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property string title: ""
    property string message: ""
    property color accent: "#ff4646"
    property bool resetVisible: true
    property bool closeVisible: false
    property bool multiple: false
    property string pageText: ""
    signal resetPressed()
    signal resetReleased()
    signal closeRequested()
    signal previousRequested()
    signal nextRequested()
    color: "#c8000000"
    Rectangle {
        anchors.centerIn: parent; width: 540; height: 370; radius: 18
        color: "#261b1d"; border.color: root.accent; border.width: 4
        ColumnLayout {
            anchors.fill:parent; anchors.margins:24; spacing:14
            RowLayout { Layout.fillWidth:true
                Text { Layout.fillWidth:true; text:root.title; color:root.accent; font.pixelSize:29; font.bold:true; horizontalAlignment:Text.AlignHCenter }
                PendantButton { visible:root.closeVisible; Layout.preferredWidth:48; text:"✕"; accent:"#888888"; onClicked:root.closeRequested() }
            }
            Text { Layout.fillWidth:true; Layout.fillHeight:true; text:root.message; color:"white"; font.pixelSize:21; font.bold:true; wrapMode:Text.Wrap; horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter }
            RowLayout { visible:root.multiple; Layout.alignment:Qt.AlignHCenter
                PendantButton { text:"◀"; Layout.preferredWidth:70; onClicked:root.previousRequested() }
                Text { text:root.pageText; color:"white"; font.pixelSize:18; font.bold:true }
                PendantButton { text:"▶"; Layout.preferredWidth:70; onClicked:root.nextRequested() }
            }
            PendantButton { visible:root.resetVisible; Layout.alignment:Qt.AlignHCenter; Layout.preferredWidth:260; text:"ALARM RESET"; accent:"#e74c3c"; onPressed:root.resetPressed(); onReleased:root.resetReleased() }
        }
    }
}
