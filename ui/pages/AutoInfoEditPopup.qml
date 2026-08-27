pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../dialogs" as Dialogs

Popup {
    id: popup
    required property var autoBackend

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(900, parent ? parent.width - 70 : 900)
    height: Math.min(620, parent ? parent.height - 60 : 620)
    Overlay.modal: Rectangle { color: "#A0000000" }
    background: Rectangle {
        color: "#151E28"
        radius: 14
        border.color: "#468CFF"
        border.width: 2
    }

    contentItem: ColumnLayout {
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: "운전정보 설정"
                color: "#8FBCFF"
                font.pixelSize: 23
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Dialogs.EditorButton {
                Layout.preferredWidth: 86
                text: "삭제"
                accent: "#D64C5B"
                visible: popup.autoBackend && popup.autoBackend.infoCount > 0
                onClicked: {
                    popup.close()
                    popup.autoBackend.deleteInfo()
                }
            }
            Dialogs.EditorButton {
                Layout.preferredWidth: 86
                text: "닫기"
                accent: "#805050"
                onClicked: popup.close()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            Text { text: "표시 명칭"; color: "#C7D1DA"; font.pixelSize: 17 }
            Dialogs.EditorButton {
                Layout.fillWidth: true
                text: popup.autoBackend ? popup.autoBackend.editingInfoName : ""
                accent: "#5C8FD8"
                onClicked: popup.autoBackend.renameInfo()
            }
        }

        Text {
            Layout.fillWidth: true
            text: "표시할 데이터를 선택하세요. 시퀀스 편집기에서 만든 데이터만 나타납니다."
            color: "#91A5B8"
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: 9
            color: popup.autoBackend && popup.autoBackend.editingInfoDataId < 0
                   ? "#253F59" : "#1B2936"
            border.color: popup.autoBackend && popup.autoBackend.editingInfoDataId < 0
                          ? "#65A1FF" : "#3B536A"
            border.width: popup.autoBackend && popup.autoBackend.editingInfoDataId < 0 ? 3 : 1
            Column {
                anchors.centerIn: parent
                Text { anchors.horizontalCenter: parent.horizontalCenter
                       text: popup.autoBackend && popup.autoBackend.editingInfoHasPlcDefault
                             ? "PLC 기본값 사용" : "데이터 참조 해제"
                       color: "white"; font.pixelSize: 17; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter
                       text: popup.autoBackend && popup.autoBackend.editingInfoHasPlcDefault
                             ? "기존 생산·목표·싸이클 정보" : "값을 표시하지 않음"
                       color: "#9FB0BE"; font.pixelSize: 13 }
            }
            MouseArea { anchors.fill: parent; onClicked: popup.autoBackend.clearInfoData() }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: dataGrid.count === 0
            text: "등록된 데이터가 없습니다.\n시퀀스 편집기의 DAT 선택 팝업에서 먼저 추가하세요."
            color: "#718394"
            font.pixelSize: 16
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        GridView {
            id: dataGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: count > 0
            clip: true
            model: popup.autoBackend ? popup.autoBackend.infoDataCards : []
            cellWidth: width / 4
            cellHeight: 116
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: card
                required property int index
                required property var modelData
                width: GridView.view.cellWidth
                height: GridView.view.cellHeight
                property int dataId: Number(modelData.id)
                property bool selectedCard: popup.autoBackend
                                                && dataId === popup.autoBackend.editingInfoDataId

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    color: card.selectedCard ? "#253F59" : "#1B2936"
                    border.color: card.selectedCard ? "#65A1FF" : "#3B536A"
                    border.width: card.selectedCard ? 3 : 1
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 9
                        spacing: 4
                        Text { Layout.fillWidth: true; text: String(card.modelData.name || "")
                               color: "#F1F5F8"; font.pixelSize: 16; font.bold: true
                               elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter }
                        Text { Layout.fillWidth: true; text: String(card.modelData.value || "0")
                               color: "#FFD166"; font.pixelSize: 20; font.bold: true
                               horizontalAlignment: Text.AlignHCenter }
                        Text { Layout.fillWidth: true; text: String(card.modelData.source || "")
                               color: "#91A5B8"; font.pixelSize: 11
                               elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: popup.autoBackend.selectInfoData(card.dataId)
                    }
                }
            }
        }
    }
}
