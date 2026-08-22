import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root
    signal dismissed()
    property var alarmRows: []
    property var operationRows: []
    property bool alarmTab: true
    modal: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(920, parent ? parent.width - 50 : 920)
    height: Math.min(650, parent ? parent.height - 50 : 650)
    padding: 18
    Overlay.modal: Rectangle { color: "#A0000000" }
    background: Rectangle { color: "#1A1F2B"; radius: 14; border.color: "#468CFF"; border.width: 2 }

    contentItem: ColumnLayout {
        spacing: 10
        Text {
            text: (root.alarmTab ? "알람 발생 이력 (최근 30일)" : "조작 이력 (최근 7일)")
                  + "   (" + list.count + "건)"
            color: "#65A1FF"; font.pixelSize: 24; font.bold: true
        }
        RowLayout {
            Button { text: "알람 이력 (30일)"; highlighted: root.alarmTab; onClicked: root.alarmTab = true }
            Button { text: "조작 이력 (7일)"; highlighted: !root.alarmTab; onClicked: root.alarmTab = false }
            Item { Layout.fillWidth: true }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 36; color: "#18FFFFFF"; radius: 5
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                Text { Layout.preferredWidth: 170; text: "일시"; color: "#AAAAAA"; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.preferredWidth: 110; text: "분류"; color: "#AAAAAA"; horizontalAlignment: Text.AlignHCenter }
                Text { visible: root.alarmTab; Layout.preferredWidth: 70; text: "코드"; color: "#AAAAAA"; horizontalAlignment: Text.AlignHCenter }
                Text { Layout.fillWidth: true; text: root.alarmTab ? "메시지" : "내용"; color: "#AAAAAA"; horizontalAlignment: Text.AlignHCenter }
            }
        }
        ListView {
            id: list; Layout.fillWidth: true; Layout.fillHeight: true
            model: root.alarmTab ? root.alarmRows : root.operationRows
            spacing: 4; clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: Rectangle {
                required property var modelData
                width: list.width; height: 44; radius: 5; color: "#0CFFFFFF"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    Text { Layout.preferredWidth: 170; text: modelData.ts || ""; color: "#DDDDDD"; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.preferredWidth: 110; text: modelData.categoryLabel || ""; color: root.alarmTab ? "#FF9999" : "#7FD3FF"; font.bold: true; horizontalAlignment: Text.AlignHCenter }
                    Text { visible: root.alarmTab; Layout.preferredWidth: 70; text: modelData.codeLabel || "-"; color: "#DDDDDD"; horizontalAlignment: Text.AlignHCenter }
                    Text { Layout.fillWidth: true; text: modelData.message || ""; color: "#DDDDDD"; elide: Text.ElideRight }
                }
            }
            Text { anchors.centerIn: parent; visible: list.count === 0; text: "기록된 이력이 없습니다."; color: "#888888"; font.pixelSize: 17 }
        }
        Button { Layout.fillWidth: true; Layout.preferredHeight: 50; text: "닫기"; onClicked: { root.close(); root.dismissed() } }
    }
}
