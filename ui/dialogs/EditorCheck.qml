import QtQuick 2.15
import QtQuick.Controls 2.15

CheckBox {
    id: control
    implicitHeight: 42
    spacing: 9
    indicator: Rectangle {
        implicitWidth: 27
        implicitHeight: 27
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 5
        color: control.checked ? "#468CFF" : "#17222e"
        border.color: control.checked ? "#7eb2ff" : "#71859a"
        border.width: 2
        Text {
            anchors.centerIn: parent
            text: "✓"
            visible: control.checked
            color: "white"
            font.pixelSize: 19
            font.bold: true
        }
    }
    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? "#ecf2f8" : "#718093"
        font.pixelSize: 15
        font.bold: true
        verticalAlignment: Text.AlignVCenter
    }
}
