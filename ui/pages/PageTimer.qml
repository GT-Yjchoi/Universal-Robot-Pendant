// Timer library page. Variable libraries are managed where they are used in
// the sequence editor, not on this page.
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property var timerModel
    required property var timerBackend
    color: "#660F161E"
    radius: 16
    border.color: "#23FFFFFF"
    border.width: 1

    property string activeName: timerBackend ? timerBackend.activeName : ""
    property bool blinkOn: timerBackend ? timerBackend.blinkOn : false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        Text {
            Layout.fillWidth: true
            text: "타이머 라이브러리"
            color: "#8FB9E8"
            font.pixelSize: 20
            font.bold: true
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: timerGrid.count === 0
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            text: "타이머가 없습니다.\n시퀀스 편집기에서 타이머를 추가하세요."
            color: "#66FFFFFF"
            font.pixelSize: 16
            wrapMode: Text.WordWrap
        }

        GridView {
            id: timerGrid
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: count > 0
            clip: true
            model: timerModel
            cacheBuffer: 2000
            boundsBehavior: Flickable.StopAtBounds
            cellWidth: Math.floor(width / 6)
            cellHeight: 110

            delegate: Item {
                width: timerGrid.cellWidth
                height: timerGrid.cellHeight
                property bool isActive: model.tname === root.activeName

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 5
                    radius: 12
                    color: isActive ? (root.blinkOn ? "#162A1E" : "#111E16") : "#1A222C"
                    border.width: isActive ? 2 : 1
                    border.color: isActive ? (root.blinkOn ? "#00FF7F" : "#007A40") : "#3E4A59"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 6
                        spacing: 4

                        Text {
                            text: model.tname
                            color: "#DDDDDD"
                            font.pixelSize: 16
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 50
                            radius: 6
                            color: timerMa.pressed ? "#34495E" : "#2C3E50"
                            border.color: timerMa.pressed ? "#468CFF" : "#3E4A59"
                            Text {
                                anchors.centerIn: parent
                                text: model.tsec
                                color: "#FFFF00"
                                font.pixelSize: 21
                                font.bold: true
                            }
                            MouseArea {
                                id: timerMa
                                anchors.fill: parent
                                onClicked: timerBackend.editTimer(model.tname)
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Item { Layout.fillWidth: true }
            Rectangle {
                Layout.preferredWidth: 130
                Layout.preferredHeight: 36
                radius: 8
                color: reorderMa.pressed ? "#594692FF" : "#26468CFF"
                border.color: "#80468CFF"
                Text {
                    anchors.centerIn: parent
                    text: "⇄ 순서 변경"
                    color: "#7EB8FF"
                    font.pixelSize: 14
                    font.bold: true
                }
                MouseArea {
                    id: reorderMa
                    anchors.fill: parent
                    onClicked: timerBackend.reorder()
                }
            }
        }
    }
}
