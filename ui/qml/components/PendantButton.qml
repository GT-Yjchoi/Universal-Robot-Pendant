import QtQuick 2.15
import QtQuick.Controls 2.15

Button {
    id: control
    property color accent: "#6f88a2"
    property color textColor: "#ffffff"
    implicitHeight: 48
    font.pixelSize: 16
    font.bold: true
    contentItem: Text {
        text: control.text; color: control.textColor
        font: control.font; horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 8
        color: control.down ? Qt.darker(control.accent, 1.35) : Qt.rgba(control.accent.r, control.accent.g, control.accent.b, 0.24)
        border.color: control.accent; border.width: control.activeFocus ? 2 : 1
    }
}
