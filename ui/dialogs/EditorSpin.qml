import QtQuick 2.15
import QtQuick.Layouts 1.15

RowLayout {
    id: root
    property int from: 0
    property int to: 100
    property int value: 0
    property int stepSize: 1
    signal valueModified(int value)
    spacing: 5

    EditorButton {
        Layout.preferredWidth: 45
        Layout.preferredHeight: 44
        text: "−"
        accent: "#62778c"
        enabled: root.value > root.from
        onClicked: root.valueModified(Math.max(root.from, root.value - root.stepSize))
    }
    Rectangle {
        Layout.preferredWidth: 86
        Layout.preferredHeight: 44
        radius: 7
        color: "#111a23"
        border.color: "#47637d"
        Text {
            anchors.centerIn: parent
            text: String(root.value)
            color: "#FFD166"
            font.pixelSize: 19
            font.bold: true
        }
    }
    EditorButton {
        Layout.preferredWidth: 45
        Layout.preferredHeight: 44
        text: "+"
        accent: "#62778c"
        enabled: root.value < root.to
        onClicked: root.valueModified(Math.min(root.to, root.value + root.stepSize))
    }
}
