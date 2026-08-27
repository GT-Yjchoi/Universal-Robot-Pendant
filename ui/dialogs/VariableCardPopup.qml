pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string kind: "bit"
    property var items: []
    property int currentId: -1
    property string titleText: kind === "bit" ? "내부비트 선택" : "데이터 선택"

    signal selected(int itemId)
    signal addRequested()
    signal renameRequested(int itemId)
    signal deleteRequested(int itemId)
    signal valueRequested(int itemId)
    signal publishRequested(int itemId)
    signal unpublishRequested(int itemId)
    signal resetRequested(int itemId)

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
        border.color: popup.kind === "bit" ? "#35A98B" : "#468CFF"
        border.width: 2
    }

    contentItem: ColumnLayout {
        spacing: 10

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: popup.titleText
                color: popup.kind === "bit" ? "#64FFDA" : "#8FBCFF"
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
            text: "카드를 짧게 누르면 선택 · 길게 누르면 이름 변경"
            color: "#91A5B8"
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
        }

        GridView {
            id: cardGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: popup.items
            cellWidth: width / 4
            cellHeight: 150
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: delegateRoot
                required property int index
                required property var modelData
                width: GridView.view.cellWidth
                height: GridView.view.cellHeight
                property bool held: false
                property int itemId: Number(modelData.id)
                property bool selectedCard: itemId === popup.currentId

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    color: delegateRoot.selectedCard ? "#253F59" : "#1B2936"
                    border.color: delegateRoot.selectedCard
                                  ? (popup.kind === "bit" ? "#64FFDA" : "#65A1FF")
                                  : "#3B536A"
                    border.width: delegateRoot.selectedCard ? 3 : 1

                    MouseArea {
                        id: selectArea
                        anchors.fill: parent
                        onPressed: delegateRoot.held = false
                        onPressAndHold: {
                            delegateRoot.held = true
                            popup.close()
                            popup.renameRequested(delegateRoot.itemId)
                        }
                        onClicked: {
                            if (delegateRoot.held)
                                return
                            popup.selected(delegateRoot.itemId)
                            popup.close()
                        }
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 5

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: String(delegateRoot.modelData.name || "")
                                color: delegateRoot.selectedCard ? "#FFFFFF" : "#E7EEF4"
                                font.pixelSize: 17
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Rectangle {
                                Layout.preferredWidth: 27
                                Layout.preferredHeight: 27
                                radius: 5
                                color: deleteMa.pressed ? "#8F2935" : "#542B33"
                                border.color: "#C65B67"
                                z: 2
                                Text { anchors.centerIn: parent; text: "×"; color: "#FF9EA8"; font.pixelSize: 18 }
                                MouseArea {
                                    id: deleteMa
                                    anchors.fill: parent
                                    onClicked: {
                                        popup.close()
                                        popup.deleteRequested(delegateRoot.itemId)
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            radius: 6
                            color: valueMa.pressed ? "#34495E" : "#263746"
                            border.color: popup.kind === "bit"
                                          ? (Boolean(delegateRoot.modelData.state) ? "#32D296" : "#708090")
                                          : "#5C8FD8"
                            z: 2
                            Text {
                                anchors.centerIn: parent
                                text: String(delegateRoot.modelData.valueText || "")
                                color: popup.kind === "bit" && Boolean(delegateRoot.modelData.state)
                                       ? "#64FFDA" : "#FFD166"
                                font.pixelSize: 19
                                font.bold: true
                            }
                            MouseArea {
                                id: valueMa
                                anchors.fill: parent
                                onClicked: {
                                    popup.close()
                                    popup.valueRequested(delegateRoot.itemId)
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 5
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 29
                                radius: 5
                                color: Boolean(delegateRoot.modelData.publish) ? "#174D41" : "#2A343E"
                                border.color: Boolean(delegateRoot.modelData.publish) ? "#35A98B" : "#53616D"
                                z: 2
                                Text {
                                    anchors.centerIn: parent
                                    text: Boolean(delegateRoot.modelData.publish)
                                          ? "PLC " + String(delegateRoot.modelData.plc || "")
                                          : (popup.kind === "data" ? "PLC 공개 설정" : "팬던트 내부")
                                    color: Boolean(delegateRoot.modelData.publish) ? "#64FFDA" : "#AAB6C0"
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    width: parent.width - 8
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: popup.publishRequested(delegateRoot.itemId)
                                }
                            }
                            Rectangle {
                                visible: popup.kind === "data" && Boolean(delegateRoot.modelData.publish)
                                Layout.preferredWidth: visible ? 42 : 0
                                Layout.preferredHeight: 29
                                radius: 5
                                color: "#542B33"
                                border.color: "#C65B67"
                                z: 2
                                Text {
                                    anchors.centerIn: parent
                                    text: "해제"
                                    color: "#FF9EA8"
                                    font.pixelSize: 10
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: {
                                        popup.close()
                                        popup.unpublishRequested(delegateRoot.itemId)
                                    }
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 29
                                radius: 5
                                color: "#2A343E"
                                border.color: "#53616D"
                                z: 2
                                Text {
                                    anchors.centerIn: parent
                                    text: String(delegateRoot.modelData.reset || "")
                                    color: "#C5D0D8"
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    width: parent.width - 8
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    onClicked: popup.resetRequested(delegateRoot.itemId)
                                }
                            }
                        }
                    }
                }
            }
        }

        EditorButton {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            text: popup.kind === "bit" ? "+ 새 내부비트 추가" : "+ 새 데이터 추가"
            accent: popup.kind === "bit" ? "#35A98B" : "#468CFF"
            onClicked: {
                popup.close()
                popup.addRequested()
            }
        }
    }
}
