import QtQuick 2.15
import QtQuick.Controls 2.15

ComboBox {
    id: control
    implicitHeight: 46
    font.pixelSize: 16
    font.bold: true

    contentItem: Text {
        leftPadding: 14
        rightPadding: 36
        text: control.displayText
        color: control.enabled ? "#ffffff" : "#718093"
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: control.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        text: "▼"
        color: "#65A1FF"
        font.pixelSize: 14
    }
    background: Rectangle {
        radius: 7
        color: control.down ? "#30465c" : "#202f3e"
        border.color: control.activeFocus ? "#65A1FF" : "#47637d"
        border.width: control.activeFocus ? 2 : 1
    }
    delegate: ItemDelegate {
        width: control.width
        height: 48
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: modelData
            color: "white"
            font.pixelSize: 16
            font.bold: true
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: highlighted ? "#355f8a" : "#1b2835"
        }
    }
    popup: Popup {
        y: control.height + 3
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 4, 360)
        padding: 2
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
        background: Rectangle {
            color: "#15212c"
            radius: 7
            border.color: "#65A1FF"
        }
    }
}
