import QtQuick 2.15
import "../qml/components" as Components

Components.PendantButton {
    id: control
    background: Rectangle {
        radius: 8
        color: control.down
               ? Qt.darker(control.accent, 1.55)
               : Qt.darker(control.accent, 2.05)
        border.color: control.accent
        border.width: control.activeFocus ? 2 : 1
    }
}
