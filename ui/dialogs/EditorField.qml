import QtQuick 2.15
import QtQuick.Controls 2.15

TextField {
    id: control
    implicitHeight: 48
    leftPadding: 13
    rightPadding: 13
    color: "#ffffff"
    placeholderTextColor: "#718093"
    selectionColor: "#468CFF"
    selectedTextColor: "white"
    font.pixelSize: 17
    background: Rectangle {
        radius: 7
        color: control.enabled ? "#111a23" : "#19232d"
        border.color: control.activeFocus ? "#65A1FF" : "#3d566d"
        border.width: control.activeFocus ? 2 : 1
    }
}
