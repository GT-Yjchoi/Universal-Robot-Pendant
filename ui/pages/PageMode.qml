// PoC: 동작모드 페이지 QML 버전 — GPU 씬그래프 렌더 + 키네틱 스크롤.
// 로직(인터록·PLC·이름)은 Python(backend)에 그대로 위임.
// 외형은 QWidget .ModeTileBtn / _get_btn_stylesheet 와 동일하게 재현.
import QtQuick
import QtQuick.Controls

Rectangle {
    id: root
    required property var modeModel
    required property var backend
    // .GlassCard 와 동일 (rgba(15,22,30,150), radius 16)
    color: "#660F161E"
    radius: 16
    border.color: "#23FFFFFF"
    border.width: 1

    property int cols: 4

    GridView {
        id: gv
        anchors.fill: parent
        anchors.margins: 14
        clip: true
        cacheBuffer: 2000                 // 위/아래 미리 GPU 노드화 → 플릭 끊김 방지
        boundsBehavior: Flickable.StopAtBounds
        model: modeModel                  // Python QAbstractListModel (context property)

        cellWidth: Math.floor(width / root.cols)
        cellHeight: 100                    // 80 min + spacing

        delegate: Item {
            width: gv.cellWidth
            height: gv.cellHeight

            Rectangle {
                anchors.fill: parent
                anchors.margins: 5
                radius: 8
                // 토글/유저모드별 색 (Python _get_btn_stylesheet 동일 값)
                color: model.checked ? "#26468CFF"          // rgba(70,140,255,0.15)
                                     : (pressArea.pressed ? "#1AFFFFFF"
                                                          : "#0DFFFFFF")  // rgba(255,255,255,0.05)
                border.width: 1
                border.color: model.checked ? "#468CFF"
                                            : "#4DFFD700"     // rgba(255,215,0,0.3) 유저모드

                Column {
                    anchors.centerIn: parent
                    spacing: 4
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: model.name
                        font.pixelSize: 16
                        font.bold: true
                        color: model.checked ? "#E0E0E0" : "#CCCCCC"
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: model.checked ? "ON" : "OFF"
                        font.pixelSize: 20
                        font.bold: true
                        color: model.checked ? "#00FF00" : "#999999"
                    }
                }

                MouseArea {
                    id: pressArea
                    anchors.fill: parent
                    onClicked: backend.toggle(index)
                    pressAndHoldInterval: 800
                    onPressAndHold: backend.longPress(index)
                }
            }
        }
    }
}
