pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property var items: []
    property int currentIndex: -1

    signal selected(int modeIndex)

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(980, parent ? parent.width - 50 : 980)
    height: Math.min(660, parent ? parent.height - 40 : 660)
    Overlay.modal: Rectangle { color: "#A0000000" }
    background: Rectangle {
        color: "#151E28"
        radius: 14
        border.color: "#8B7FE8"
        border.width: 2
    }

    contentItem: ColumnLayout {
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: "JMP 조건 모드 선택"
                color: "#B9B1FF"
                font.pixelSize: 23
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            EditorButton {
                Layout.preferredWidth: 86
                text: "닫기"
                accent: "#805050"
                onClicked: popup.close()
            }
        }

        Text {
            Layout.fillWidth: true
            text: "조건으로 사용할 모드 카드를 선택하세요. 현재 모드 상태도 함께 표시됩니다."
            color: "#91A5B8"
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
        }

        GridView {
            id: modeGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: popup.items
            cellWidth: width / 4
            cellHeight: 112
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: cardRoot
                required property var modelData
                width: GridView.view.cellWidth
                height: GridView.view.cellHeight
                property int modeIndex: Number(modelData.index)
                property bool selectedCard: modeIndex === popup.currentIndex

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    color: cardRoot.selectedCard ? "#332F57" : "#1B2936"
                    border.color: cardRoot.selectedCard ? "#B9B1FF" : "#3B536A"
                    border.width: cardRoot.selectedCard ? 3 : 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 5
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "[" + (cardRoot.modeIndex + 1 < 10 ? "0" : "")
                                      + String(cardRoot.modeIndex + 1) + "]"
                                color: "#8E9FB0"
                                font.pixelSize: 13
                                font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: Boolean(cardRoot.modelData.state) ? "ON" : "OFF"
                                color: Boolean(cardRoot.modelData.state) ? "#64FFDA" : "#8E9FB0"
                                font.pixelSize: 14
                                font.bold: true
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: String(cardRoot.modelData.name || "")
                            color: "#FFFFFF"
                            font.pixelSize: 16
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.WordWrap
                            elide: Text.ElideRight
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            popup.selected(cardRoot.modeIndex)
                            popup.close()
                        }
                    }
                }
            }
        }
    }
}
