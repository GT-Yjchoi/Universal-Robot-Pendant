// 위치설정 페이지 QML(GPU). 렌더/스크롤만, 로직(teach·값편집·PLC·실시간추종)
// 은 Python(backend) 그대로(verbatim). 좌:nav+8축그리드+teach / 중:시퀀스
// 선택+미리보기(GPU 스크롤) / 우:밸브(QML 재사용).
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

Rectangle {
    id: root
    required property var axisModel
    required property var previewModel
    required property var valveModel
    required property var valveBackend
    required property var posBackend
    color: "#660F161E"; radius: 16
    border.color: "#23FFFFFF"; border.width: 1

    SequenceMonitorPopup {
        id: sequenceMonitorPopup
        posBackend: root.posBackend
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 16

        // ===== LEFT (4): nav + 8축 그리드 + teach =====
        ColumnLayout {
            Layout.preferredWidth: 4; Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 8

            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: false
                Layout.preferredHeight: 46; Layout.maximumHeight: 46
                spacing: 10
                Rectangle {
                    Layout.preferredWidth: 45; Layout.preferredHeight: 42; radius: 6
                    color: pPrev.pressed ? "#4D468CFF" : "#1AFFFFFF"
                    border.color: "#4DFFFFFF"; border.width: 1
                    opacity: posBackend && posBackend.canPrev ? 1.0 : 0.35
                    Text { anchors.centerIn: parent; text: "◀"; color: "white"
                           font.pixelSize: 18; font.bold: true }
                    MouseArea { id: pPrev; anchors.fill: parent
                        onClicked: if (posBackend) posBackend.prevPoint() }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.preferredHeight: 42; radius: 6
                    color: pName.pressed ? "#33468CFF" : "#1AFFFFFF"
                    border.color: "#66468CFF"; border.width: 1
                    Text { anchors.centerIn: parent
                           text: posBackend ? posBackend.pointName : "위치 없음"
                           color: "white"; font.pixelSize: 18; font.bold: true
                           elide: Text.ElideRight; width: parent.width - 16
                           horizontalAlignment: Text.AlignHCenter }
                    MouseArea { id: pName; anchors.fill: parent
                        onClicked: if (posBackend) posBackend.showNameCard() }
                }
                Rectangle {
                    Layout.preferredWidth: 45; Layout.preferredHeight: 42; radius: 6
                    color: pReo.pressed ? "#4D468CFF" : "#1AFFFFFF"
                    border.color: "#80808080"; border.width: 1
                    Text { anchors.centerIn: parent; text: "☰"; color: "white"
                           font.pixelSize: 22 }
                    MouseArea { id: pReo; anchors.fill: parent
                        onClicked: if (posBackend) posBackend.reorder() }
                }
                Rectangle {
                    Layout.preferredWidth: 45; Layout.preferredHeight: 42; radius: 6
                    color: pNext.pressed ? "#4D468CFF" : "#1AFFFFFF"
                    border.color: "#4DFFFFFF"; border.width: 1
                    opacity: posBackend && posBackend.canNext ? 1.0 : 0.35
                    Text { anchors.centerIn: parent; text: "▶"; color: "white"
                           font.pixelSize: 18; font.bold: true }
                    MouseArea { id: pNext; anchors.fill: parent
                        onClicked: if (posBackend) posBackend.nextPoint() }
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "#26000000"; radius: 10
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true; spacing: 10
                        Text { text: "축"; color: "#99FFFFFF"; font.pixelSize: 16
                               font.bold: true; Layout.preferredWidth: 40
                               horizontalAlignment: Text.AlignHCenter }
                        Text { text: "현재위치"; color: "#99FFFFFF"; font.pixelSize: 16
                               font.bold: true; Layout.fillWidth: true
                               horizontalAlignment: Text.AlignHCenter }
                        Text { text: "기억위치"; color: "#99FFFFFF"; font.pixelSize: 16
                               font.bold: true; Layout.fillWidth: true
                               horizontalAlignment: Text.AlignHCenter }
                        Text { text: "속도%"; color: "#99FFFFFF"; font.pixelSize: 16
                               font.bold: true; Layout.preferredWidth: 70
                               horizontalAlignment: Text.AlignHCenter }
                    }
                    ListView {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; model: axisModel; spacing: 8
                        boundsBehavior: Flickable.StopAtBounds
                        interactive: contentHeight > height
                        delegate: RowLayout {
                            width: ListView.view ? ListView.view.width : 0
                            height: model.avis ? 46 : 0
                            visible: model.avis
                            spacing: 10
                            Text { text: model.aname; color: "#DDDDDD"
                                   font.pixelSize: 20; font.bold: true
                                   Layout.preferredWidth: 40
                                   horizontalAlignment: Text.AlignHCenter }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 44
                                radius: 6; color: "#1FFFFFFF"
                                border.color: "#8064FFDA"
                                border.width: 1
                                Text { anchors.centerIn: parent; text: model.acur
                                       color: "white"; font.pixelSize: 21; font.bold: true }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 44
                                radius: 6; color: cMa.pressed ? "#3364FFDA" : "#0DFFFFFF"
                                border.color: "#26FFFFFF"; border.width: 1
                                Text { anchors.centerIn: parent; text: model.asaved
                                       color: "#64FFDA"; font.pixelSize: 21; font.bold: true }
                                MouseArea { id: cMa; anchors.fill: parent
                                    onClicked: if (posBackend)
                                        posBackend.valueClicked(index, "coords") }
                            }
                            Rectangle {
                                Layout.preferredWidth: 70; Layout.preferredHeight: 44
                                radius: 6; color: sMa.pressed ? "#33FFD280" : "#0DFFFFFF"
                                border.color: "#26FFFFFF"; border.width: 1
                                Text { anchors.centerIn: parent; text: model.aspeed
                                       color: "#FFD280"; font.pixelSize: 21; font.bold: true }
                                MouseArea { id: sMa; anchors.fill: parent
                                    onClicked: if (posBackend)
                                        posBackend.valueClicked(index, "speed") }
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 55; radius: 12
                property bool en: posBackend ? posBackend.teachEnabled : true
                color: !en ? "#22FFFFFF"
                            : (tMa.pressed ? "#5546C864" : "#2546C864")
                border.width: 2
                border.color: en ? "#46C864" : "#33FFFFFF"
                Text { anchors.centerIn: parent; text: "현재 위치 기억 (TEACH)"
                       color: parent.en ? "#DFFFE6" : "#888888"
                       font.pixelSize: 18; font.bold: true }
                MouseArea { id: tMa; anchors.fill: parent
                    enabled: parent.en
                    onClicked: if (posBackend) posBackend.teachClicked() }
            }
        }

        // ===== MID (4): 시퀀스 선택 + 미리보기 =====
        ColumnLayout {
            Layout.preferredWidth: 4; Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 10
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: false
                Layout.preferredHeight: 44; Layout.maximumHeight: 44
                spacing: 10
                Text { text: "동작 순서"; color: "#E9EEF3"
                       font.pixelSize: 18; font.bold: true }
                Rectangle {
                    Layout.preferredWidth: 108
                    Layout.preferredHeight: 40
                    radius: 6
                    color: editSequenceMa.pressed ? "#2D69C4" : "#315D86"
                    border.color: "#65A1FF"
                    border.width: 1
                    Text {
                        anchors.centerIn: parent
                        text: "동작 편집"
                        color: "white"
                        font.pixelSize: 15
                        font.bold: true
                    }
                    MouseArea {
                        id: editSequenceMa
                        anchors.fill: parent
                        onClicked: if (posBackend) posBackend.openSeqEditor()
                    }
                }
                Item { Layout.fillWidth: true }
                ComboBox {
                    id: seqCombo
                    Layout.preferredWidth: 180; Layout.preferredHeight: 40
                    model: posBackend ? posBackend.seqKeys : []
                    currentIndex: posBackend ? posBackend.seqIndex : 0
                    onActivated: if (posBackend) posBackend.seqChanged(currentIndex)

                    background: Rectangle {
                        radius: 4
                        color: "#1AFFFFFF"
                        border.color: "#4DFFFFFF"; border.width: 1
                    }
                    contentItem: Text {
                        leftPadding: 10; rightPadding: seqCombo.indicator.width + 6
                        text: seqCombo.displayText
                        color: "white"; font.pixelSize: 16; font.bold: true
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    indicator: Text {
                        x: seqCombo.width - width - 10
                        y: (seqCombo.height - height) / 2
                        text: "▾"; color: "#9CC8FF"; font.pixelSize: 16
                    }
                    popup: Popup {
                        y: seqCombo.height + 2
                        width: seqCombo.width
                        implicitHeight: Math.min(contentItem.implicitHeight + 8, 360)
                        padding: 4
                        background: Rectangle {
                            color: "#141E28"; radius: 6
                            border.color: "#468CFF"; border.width: 1
                        }
                        contentItem: ListView {
                            clip: true
                            implicitHeight: contentHeight
                            model: seqCombo.popup.visible ? seqCombo.delegateModel : null
                            currentIndex: seqCombo.highlightedIndex
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollIndicator.vertical: ScrollIndicator {}
                        }
                    }
                    delegate: ItemDelegate {
                        width: seqCombo.width
                        height: 44
                        contentItem: Text {
                            text: modelData
                            color: "white"; font.pixelSize: 18; font.bold: true
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: 10; elide: Text.ElideRight
                        }
                        background: Rectangle {
                            color: highlighted ? "#468CFF" : "transparent"
                            radius: 4
                        }
                        highlighted: seqCombo.highlightedIndex === index
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "#33000000"; radius: 8
                border.color: "#1AFFFFFF"; border.width: 2
                ListView {
                    id: prev
                    anchors.fill: parent; anchors.margins: 4
                    clip: true; model: previewModel; spacing: 0
                    cacheBuffer: 2000
                    boundsBehavior: Flickable.StopAtBounds
                    currentIndex: posBackend ? posBackend.hiRow : -1
                    onCurrentIndexChanged:
                        if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Center)
                    delegate: Rectangle {
                        width: prev.width; height: 40
                        color: model.phi ? "#4600E5FF" : "transparent"
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 8; width: parent.width - 12
                            text: model.ptext
                            color: model.pcomment ? "#FFD700" : "#BBBBBB"
                            font.pixelSize: 14; elide: Text.ElideRight
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width
                                    height: 1; color: "#0DFFFFFF" }
                        MouseArea {
                            anchors.fill: parent
                            preventStealing: false
                            onClicked: sequenceMonitorPopup.open()
                        }
                    }
                }
            }
        }

        // ===== RIGHT (2): 밸브 (QML 재사용) =====
        Item {
            Layout.preferredWidth: 2; Layout.fillWidth: true; Layout.fillHeight: true
            GridView {
                id: vv
                anchors.fill: parent
                clip: true; model: valveModel
                cacheBuffer: 1600
                boundsBehavior: Flickable.StopAtBounds
                cellWidth: Math.floor(width / 2)
                cellHeight: 70
                delegate: Item {
                    width: vv.cellWidth; height: vv.cellHeight
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 5; radius: 8
                        color: model.vchecked ? "#CCFF7800"
                              : (vMa.pressed ? "#33FFFFFF" : "#14FFFFFF")
                        border.width: model.vchecked ? 2 : 1
                        border.color: model.vchecked ? "#FF9900" : "#33FFFFFF"
                        Text { anchors.centerIn: parent; width: parent.width - 12
                               horizontalAlignment: Text.AlignHCenter
                               wrapMode: Text.WordWrap; text: model.vname
                               color: model.vchecked ? "white" : "#DDDDDD"
                               font.pixelSize: 14; font.bold: true }
                        MouseArea {
                            id: vMa; anchors.fill: parent
                            onClicked: if (model.vmode === "toggle")
                                valveBackend.valveToggle(model.vbit, !model.vchecked)
                            onPressed: if (model.vmode !== "toggle")
                                valveBackend.valvePressed(model.vbit)
                            onReleased: if (model.vmode !== "toggle")
                                valveBackend.valveReleased(model.vbit)
                        }
                    }
                }
            }
            Rectangle {
                anchors.fill: parent; radius: 10; color: "#8C000000"
                visible: valveBackend ? valveBackend.locked : false
                Text { anchors.centerIn: parent; horizontalAlignment: Text.AlignHCenter
                       text: "자동 중에는\n사용할 수 없습니다"
                       color: "white"; font.pixelSize: 18; font.bold: true }
                MouseArea { anchors.fill: parent }
            }
        }
    }
}
