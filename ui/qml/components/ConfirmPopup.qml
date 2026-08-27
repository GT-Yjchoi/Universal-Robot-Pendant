import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string title: "확인"
    property string message: ""
    property string acceptText: "확인"
    property string rejectText: "취소"
    readonly property bool rejectVisible: rejectText.trim().length > 0
    signal accepted()
    signal rejected()
    modal: true; focus: true; closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay; width: 440; height: 260
    Overlay.modal: Rectangle { color: "#a0000000" }
    background: Rectangle { color: "#19222d"; radius: 14; border.color: "#468cff"; border.width: 2 }
    contentItem: ColumnLayout {
        spacing: 18
        Text { Layout.fillWidth: true; text: popup.title; color: "#ffd280"; font.pixelSize: 24; font.bold: true; horizontalAlignment: Text.AlignHCenter }
        Text { Layout.fillWidth: true; Layout.fillHeight: true; text: popup.message; color: "#eeeeee"; font.pixelSize: 17; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        RowLayout {
            Layout.fillWidth: true; spacing: popup.rejectVisible ? 12 : 0
            PendantButton {
                visible: popup.rejectVisible
                Layout.fillWidth: visible
                Layout.preferredWidth: visible ? 1 : 0
                text: popup.rejectText; accent: "#b65252"
                onClicked: { popup.close(); popup.rejected() }
            }
            PendantButton {
                Layout.fillWidth: true; Layout.preferredWidth: 1
                text: popup.acceptText; accent: "#468cff"
                onClicked: { popup.close(); popup.accepted() }
            }
        }
    }
}
