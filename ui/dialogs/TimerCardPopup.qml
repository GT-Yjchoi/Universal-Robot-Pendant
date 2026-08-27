pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property var items: []
    property string currentName: ""
    signal selected(string name)
    signal renameRequested(string name)

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(940, parent ? parent.width - 60 : 940)
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
                text: "타이머 선택"
                color: "#FFD280"
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
            cellHeight: 104
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: delegateRoot
                required property int index
                required property var modelData
                width: GridView.view.cellWidth
                height: GridView.view.cellHeight
                property bool held: false
                property bool direct: Boolean(modelData.direct)
                property string timerName: String(modelData.name || "")
                property bool selectedCard: timerName === popup.currentName

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    color: delegateRoot.selectedCard ? "#253F59" : "#1B2936"
                    border.color: delegateRoot.selectedCard ? "#65A1FF" : "#3B536A"
                    border.width: delegateRoot.selectedCard ? 3 : 1

                    Column {
                        anchors.centerIn: parent
                        width: parent.width - 20
                        spacing: 7
                        Text {
                            width: parent.width
                            text: delegateRoot.direct ? "직접 설정" : delegateRoot.timerName
                            color: delegateRoot.selectedCard ? "#8FBCFF" : "#F1F5F8"
                            font.pixelSize: 18
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: delegateRoot.direct
                                  ? "스텝별 시간 입력"
                                  : Number(delegateRoot.modelData.seconds).toFixed(2) + " s"
                            color: delegateRoot.direct ? "#91A5B8" : "#FFD166"
                            font.pixelSize: 16
                            font.bold: !delegateRoot.direct
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        onPressed: delegateRoot.held = false
                        onPressAndHold: {
                            if (delegateRoot.direct)
                                return
                            delegateRoot.held = true
                            popup.close()
                            popup.renameRequested(delegateRoot.timerName)
                        }
                        onClicked: {
                            if (delegateRoot.held)
                                return
                            popup.selected(delegateRoot.timerName)
                            popup.close()
                        }
                    }
                }
            }
        }
    }
}
