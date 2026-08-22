import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string title: "선택"
    property var items: []
    property int columns: 4
    signal selected(int index, string value)
    signal rejected()
    modal: true; focus: true; closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay; width: Math.min(900, parent ? parent.width-60 : 900); height: Math.min(620, parent ? parent.height-60 : 620)
    Overlay.modal: Rectangle { color: "#a0000000" }
    background: Rectangle { color: "#151e28"; radius: 14; border.color: "#468cff"; border.width: 2 }
    contentItem: ColumnLayout {
        spacing: 10
        RowLayout { Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: popup.title; color: "#ffd280"; font.pixelSize: 22; font.bold: true; horizontalAlignment: Text.AlignHCenter }
            PendantButton { Layout.preferredWidth: 80; text: "닫기"; accent: "#805050"; onClicked: { popup.close(); popup.rejected() } }
        }
        GridView {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            model: popup.items; cellWidth: width/popup.columns; cellHeight: 78
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Item {
                required property int index; required property var modelData
                width: GridView.view.cellWidth; height: GridView.view.cellHeight
                PendantButton { anchors.fill: parent; anchors.margins: 5; text: String(modelData); onClicked: { popup.selected(index,String(modelData)); popup.close() } }
            }
        }
    }
}
