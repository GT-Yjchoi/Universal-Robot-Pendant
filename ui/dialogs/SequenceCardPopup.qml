pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property var items: []
    property int currentIndex: -1
    signal selected(int index)
    signal renameRequested(int index)

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(900, parent ? parent.width - 60 : 900)
    height: Math.min(610, parent ? parent.height - 60 : 610)
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
                text: "시퀀스 프로그램 선택"
                color: "#9CC8FF"
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
            text: "카드를 선택하세요. SUB 카드를 길게 누르면 이름을 변경할 수 있습니다."
            color: "#91A5B8"
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
        }

        GridView {
            id: programGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: popup.items
            cellWidth: width / 3
            cellHeight: 124
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: cardRoot
                required property int index
                required property var modelData
                width: GridView.view.cellWidth
                height: GridView.view.cellHeight
                property bool selectedCard: index === popup.currentIndex
                property string programKind: String(modelData.kind || "SUB")

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 7
                    radius: 10
                    color: cardRoot.selectedCard ? "#253F59" : "#1B2936"
                    border.color: cardRoot.selectedCard ? "#65A1FF" : "#3B536A"
                    border.width: cardRoot.selectedCard ? 3 : 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 11
                        spacing: 5
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: cardRoot.programKind
                                color: cardRoot.programKind === "MAIN" ? "#64FFDA"
                                       : cardRoot.programKind === "MONITOR" ? "#FFD166"
                                       : "#B9B1FF"
                                font.pixelSize: 13
                                font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: String(cardRoot.modelData.stepCount) + " STEP"
                                color: "#8E9FB0"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            text: String(cardRoot.modelData.name || "")
                            color: cardRoot.selectedCard ? "#9CC8FF" : "#FFFFFF"
                            font.pixelSize: 19
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            popup.selected(cardRoot.index)
                            popup.close()
                        }
                        onPressAndHold: function(mouse) {
                            if (cardRoot.programKind === "SUB") {
                                mouse.accepted = true
                                popup.renameRequested(cardRoot.index)
                                popup.close()
                            }
                        }
                    }
                }
            }
        }
    }
}
