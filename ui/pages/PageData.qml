// 금형데이터 페이지 QML(GPU). 리스트 2개 GPU 스크롤. 로직 Python.
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property var fileModel
    required property var previewModel
    required property var dataBackend
    color: "#660F161E"; radius: 16
    border.color: "#23FFFFFF"; border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 25

        // LEFT: 파일 목록 (4)
        ColumnLayout {
            Layout.preferredWidth: 4; Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 6
            Text { text: dataBackend ? dataBackend.listHeader : ""
                   color: "#B3FFFFFF"; font.pixelSize: 16; font.bold: true }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "#40000000"; radius: 10
                border.color: "#26FFFFFF"; border.width: 1
                ListView {
                    id: fileView
                    anchors.fill: parent; anchors.margins: 4
                    clip: true; model: fileModel; spacing: 0
                    cacheBuffer: 1600
                    boundsBehavior: Flickable.StopAtBounds
                    currentIndex: dataBackend ? dataBackend.selIndex : -1
                    delegate: Rectangle {
                        width: fileView.width; height: 45
                        color: ListView.isCurrentItem ? "#40468CFF" : "transparent"
                        radius: 6
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 15; text: model.display
                            color: ListView.isCurrentItem ? "white" : "#EEEEEE"
                            font.pixelSize: 16
                            font.bold: ListView.isCurrentItem
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width
                                    height: 1; color: "#0DFFFFFF" }
                        MouseArea { anchors.fill: parent
                            onClicked: if (dataBackend) dataBackend.selectFile(index) }
                    }
                }
            }
        }

        // RIGHT: 상세 + 미리보기 + 버튼 (6)
        ColumnLayout {
            Layout.preferredWidth: 6; Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 10
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 45
                color: "#33000000"; radius: 8
                Text {
                    anchors.centerIn: parent
                    text: dataBackend ? dataBackend.infoText : ""
                    color: "#FFD280"; font.pixelSize: 16; font.bold: true
                }
            }
            Text { text: dataBackend ? dataBackend.previewHeader : ""
                   color: "#B3FFFFFF"; font.pixelSize: 15 }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "#40000000"; radius: 8
                border.color: "#1AFFFFFF"; border.width: 1
                ListView {
                    id: prevView
                    anchors.fill: parent; anchors.margins: 4
                    clip: true; model: previewModel; spacing: 0
                    cacheBuffer: 2000
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Item {
                        width: prevView.width; height: 32
                        Text { anchors.verticalCenter: parent.verticalCenter
                               x: 10; text: model.display
                               color: "#CCCCCC"; font.pixelSize: 14 }
                    }
                }
            }
            RowLayout {
                // 중첩 Layout 은 fillHeight 기본 true → 명시적으로 끄고 높이 고정
                // (안 그러면 미리보기와 세로공간을 반씩 나눠 버튼이 거대해짐)
                Layout.fillWidth: true
                Layout.fillHeight: false
                Layout.preferredHeight: 65
                Layout.maximumHeight: 65
                spacing: 12
                Repeater {
                    model: dataBackend ? dataBackend.buttons : []
                    delegate: Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        radius: 12
                        color: bMa.pressed ? "#4DFFFFFF" : "#0DFFFFFF"
                        border.width: 2; border.color: modelData.color
                        Text {
                            anchors.centerIn: parent
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData.text; color: modelData.color
                            font.pixelSize: 16; font.bold: true
                        }
                        MouseArea { id: bMa; anchors.fill: parent
                            onClicked: if (dataBackend) dataBackend.btnClicked(index) }
                    }
                }
            }
        }
    }
}
