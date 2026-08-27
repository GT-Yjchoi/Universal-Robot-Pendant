// 수동운전 페이지 QML(GPU) — 렌더/스크롤만. 로직 전부 Python.
// 좌:축위치(2) 중:IO(5) 우:밸브(3). 외형은 QWidget 판과 동일 재현.
import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    required property var axisModel
    required property var ioInModel
    required property var ioOutModel
    required property var valveModel
    required property var ioBackend
    required property var valveBackend
    color: "#660F161E"          // .GlassCard
    radius: 16
    border.color: "#23FFFFFF"
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 20

        // ===== LEFT: 축 위치 (ratio 2) =====
        ColumnLayout {
            Layout.preferredWidth: 2
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Text {
                text: "현재 위치"
                color: "#DDDDDD"; font.pixelSize: 18; font.bold: true
            }
            Repeater {
                model: axisModel
                delegate: RowLayout {
                    visible: model.avisible
                    Layout.fillWidth: true
                    height: visible ? 44 : 0
                    spacing: 6
                    Text {
                        text: model.aname
                        color: "#CCCCCC"; font.pixelSize: 18; font.bold: true
                        Layout.preferredWidth: 36
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 40
                        radius: 6
                        color: "#14FFFFFF"
                        border.color: "#23FFFFFF"; border.width: 1
                        RowLayout {
                            anchors.fill: parent
                            anchors.rightMargin: 6
                            Text {
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignRight
                                text: model.avalue
                                color: "white"; font.pixelSize: 22; font.bold: true
                            }
                            Text {
                                text: "mm"
                                color: "#A0E9EEF3"; font.pixelSize: 13; font.bold: true
                                Layout.preferredWidth: 28
                            }
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }   // 상단 정렬
        }

        // ===== MIDDLE: IO (ratio 5) =====
        RowLayout {
            Layout.preferredWidth: 5
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            // 입력 컬럼
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                Text { text: ioBackend ? ioBackend.inTitle : ""; color: "#E9EEF3"
                        font.pixelSize: 16; font.bold: true }
                ListView {
                    id: inView
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    model: ioInModel
                    cacheBuffer: 1200
                    boundsBehavior: Flickable.StopAtBounds
                    spacing: 8
                    delegate: Row {
                        spacing: 10
                        Rectangle {
                            width: 34; height: 22; radius: 10
                            color: model.on ? "#F5468CFF" : "#E6000000"
                            border.width: 1
                            border.color: model.on ? "#DC8CC8FF" : "#23FFFFFF"
                        }
                        Text {
                            text: model.label; color: "#E9EEF3"
                            font.pixelSize: 19
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
            // 출력 컬럼
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                Text { text: ioBackend ? ioBackend.outTitle : ""; color: "#E9EEF3"
                        font.pixelSize: 16; font.bold: true }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    model: ioOutModel
                    cacheBuffer: 1200
                    boundsBehavior: Flickable.StopAtBounds
                    spacing: 8
                    delegate: Row {
                        spacing: 10
                        Rectangle {
                            width: 34; height: 22; radius: 10
                            color: model.on ? "#F5FF6923" : "#E6000000"
                            border.width: 1
                            border.color: model.on ? "#DCFFAA78" : "#23FFFFFF"
                        }
                        Text {
                            text: model.label; color: "#E9EEF3"
                            font.pixelSize: 19
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }

        // ===== RIGHT: 밸브 (ratio 3) =====
        Item {
            Layout.preferredWidth: 3
            Layout.fillWidth: true
            Layout.fillHeight: true

            GridView {
                id: valveView
                anchors.fill: parent
                clip: true
                model: valveModel
                cacheBuffer: 1600
                boundsBehavior: Flickable.StopAtBounds
                cellWidth: Math.floor(width / 2)
                cellHeight: 70
                delegate: Item {
                    width: valveView.cellWidth
                    height: valveView.cellHeight
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 5
                        radius: 8
                        color: model.vchecked ? "#CCFF7800"           // 주황 ON
                                              : (vMa.pressed ? "#33FFFFFF"
                                                             : "#14FFFFFF")
                        border.width: model.vchecked ? 2 : 1
                        border.color: model.vchecked ? "#FF9900" : "#33FFFFFF"
                        Text {
                            anchors.centerIn: parent
                            width: parent.width - 12
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: model.vname
                            color: model.vchecked ? "white" : "#DDDDDD"
                            font.pixelSize: 14; font.bold: true
                        }
                        MouseArea {
                            id: vMa
                            anchors.fill: parent
                            onClicked: {
                                if (model.vmode === "toggle")
                                    valveBackend.valveToggle(model.vbit, !model.vchecked)
                            }
                            onPressed: {
                                if (model.vmode !== "toggle")
                                    valveBackend.valvePressed(model.vbit)
                            }
                            onReleased: {
                                if (model.vmode !== "toggle")
                                    valveBackend.valveReleased(model.vbit)
                            }
                        }
                    }
                }
            }
            // 자동 중 잠금 오버레이
            Rectangle {
                anchors.fill: parent
                radius: 10
                color: "#8C000000"
                visible: valveBackend ? valveBackend.locked : false
                Text {
                    anchors.centerIn: parent
                    horizontalAlignment: Text.AlignHCenter
                    text: "자동 중에는\n사용할 수 없습니다"
                    color: "white"; font.pixelSize: 18; font.bold: true
                }
                MouseArea { anchors.fill: parent }   // 입력 가로챔
            }
        }
    }
}
