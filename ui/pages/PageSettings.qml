// 설정 페이지 QML(GPU). 7탭. 렌더/스크롤만, 로직 전부 Python(backend)에서
// page_settings.py 와 동일(verbatim). 안전탭(valve/param/interlock)의 PLC
// 패킹·주소·스케일은 한 글자도 안 바뀜 — 값 출처만 위젯→모델(동일값).
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls

Rectangle {
    id: root
    required property var ioModel
    required property var paramModel
    required property var valveModel
    required property var alarmModel
    required property var wifiModel
    required property var ilModeModel
    required property var ilGroupModel
    required property var settingsBackend
    color: "#660F161E"; radius: 16
    border.color: "#23FFFFFF"; border.width: 1

    readonly property var tabNames: ["일반 설정","IO설정","시스템 파라미터",
        "밸브 설정","알람 메시지","인터록 설정","네트워크"]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        // ===== 탭 바 =====
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: false
            Layout.preferredHeight: 46
            Layout.maximumHeight: 46
            spacing: 4
            Repeater {
                model: root.tabNames
                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 8
                    property bool sel: stack.currentIndex === index
                    color: sel ? "#33468CFF" : (tbMa.pressed ? "#1AFFFFFF" : "transparent")
                    border.width: 1
                    border.color: sel ? "#468CFF" : "#26FFFFFF"
                    Text {
                        anchors.centerIn: parent
                        text: modelData
                        color: sel ? "#9CC8FF" : "#AAAAAA"
                        font.pixelSize: 14; font.bold: sel
                    }
                    MouseArea { id: tbMa; anchors.fill: parent
                        onClicked: { stack.currentIndex = index
                                     if (settingsBackend) settingsBackend.tabChanged(index) } }
                }
            }
        }

        StackLayout {
            id: stack
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: 0

            // ---------- [0] 일반 설정 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 20
                    // PLC
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: false
                        Layout.preferredHeight: 100
                        Layout.minimumHeight: 100
                        spacing: 4
                        Text { text: "PLC 통신 설정"; color: "#00E5FF"
                               font.pixelSize: 15; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            color: "transparent"; radius: 8
                            border.color: "#6600E5FF"; border.width: 1
                            RowLayout {
                            anchors.fill: parent; anchors.margins: 8; spacing: 12
                            Text { text: "IP 주소:"; color: "white"; font.pixelSize: 14 }
                            Rectangle {
                                Layout.preferredWidth: 200; Layout.preferredHeight: 40
                                radius: 6; color: "#1AFFFFFF"
                                border.color: ipMa.pressed ? "#468CFF" : "#4DFFFFFF"
                                border.width: 1
                                Text { anchors.centerIn: parent
                                       text: settingsBackend ? settingsBackend.ipText : ""
                                       color: "#FFD280"; font.pixelSize: 16; font.bold: true }
                                MouseArea { id: ipMa; anchors.fill: parent
                                    onClicked: if (settingsBackend) settingsBackend.editIp() }
                            }
                            Text { text: "포트:"; color: "white"; font.pixelSize: 14 }
                            Rectangle {
                                Layout.preferredWidth: 100; Layout.preferredHeight: 40
                                radius: 6; color: "#1AFFFFFF"
                                border.color: poMa.pressed ? "#468CFF" : "#4DFFFFFF"
                                border.width: 1
                                Text { anchors.centerIn: parent
                                       text: settingsBackend ? settingsBackend.portText : ""
                                       color: "#FFD280"; font.pixelSize: 16; font.bold: true }
                                MouseArea { id: poMa; anchors.fill: parent
                                    onClicked: if (settingsBackend) settingsBackend.editPort() }
                            }
                            Rectangle {
                                Layout.preferredWidth: 100; Layout.preferredHeight: 40
                                radius: 6
                                property bool conn: settingsBackend ? settingsBackend.plcConnected : false
                                color: cnMa.pressed ? "#33FFFFFF"
                                      : (conn ? "#26FF4646" : "#2600FF00")
                                border.width: 1
                                border.color: conn ? "#FF4646" : "#00FF00"
                                Text { anchors.centerIn: parent
                                       text: settingsBackend ? settingsBackend.connText : "연결"
                                       color: parent.conn ? "#FF4646" : "#00FF00"
                                       font.pixelSize: 14; font.bold: true }
                                MouseArea { id: cnMa; anchors.fill: parent
                                    onClicked: if (settingsBackend) settingsBackend.connectClicked() }
                            }
                            Text {
                                text: settingsBackend ? settingsBackend.statusText : "● Disconnected"
                                color: settingsBackend ? settingsBackend.statusColor : "#FF4646"
                                font.pixelSize: 14; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            }
                        }
                    }
                    // 언어
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: false
                        Layout.preferredHeight: 92
                        Layout.minimumHeight: 92
                        spacing: 4
                        Text { text: "환경 설정"; color: "#DDDDDD"
                               font.pixelSize: 15; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            color: "transparent"; radius: 8
                            border.color: "#26FFFFFF"; border.width: 1
                            RowLayout {
                            anchors.fill: parent; anchors.margins: 8; spacing: 12
                            Text { text: "언어 (Language)"; color: "white"
                                   font.pixelSize: 14; font.bold: true }
                            Repeater {
                                model: [["KR","🇰🇷 한국어"],["EN","🇺🇸 English"]]
                                delegate: Rectangle {
                                    Layout.preferredWidth: 120; Layout.preferredHeight: 40
                                    radius: 20
                                    property bool act: settingsBackend
                                        && settingsBackend.lang === modelData[0]
                                    color: act ? "#33468CFF" : "#0DFFFFFF"
                                    border.width: 2
                                    border.color: act ? "#468CFF" : "#1AFFFFFF"
                                    Text { anchors.centerIn: parent; text: modelData[1]
                                           color: act ? "#468CFF" : "#AAAAAA"
                                           font.pixelSize: 13; font.bold: true }
                                    MouseArea { anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.setLang(modelData[0]) }
                                }
                            }
                            Item { Layout.fillWidth: true }
                            }
                        }
                    }
                    // 화면 밝기
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: false
                        Layout.preferredHeight: 92
                        Layout.minimumHeight: 92
                        spacing: 4
                        Text { text: "화면 밝기"; color: "#FFD280"
                               font.pixelSize: 15; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            color: "transparent"; radius: 8
                            border.color: "#33FFD280"; border.width: 1
                            RowLayout {
                            anchors.fill: parent; anchors.margins: 8; spacing: 12
                            Text { text: "밝기"; color: "white"
                                   font.pixelSize: 14; font.bold: true }
                            Rectangle {
                                Layout.preferredWidth: 44; Layout.preferredHeight: 40
                                radius: 8; color: brDn.pressed ? "#33FFD280" : "#15FFD280"
                                border.color: "#66FFD280"; border.width: 1
                                Text { anchors.centerIn: parent; text: "−"
                                       color: "#FFD280"; font.pixelSize: 22; font.bold: true }
                                MouseArea { id: brDn; anchors.fill: parent
                                    onClicked: if (settingsBackend)
                                        settingsBackend.setBrightness(
                                            Math.max(10, settingsBackend.brightness - 10)) }
                            }
                            Slider {
                                id: brSlider
                                Layout.fillWidth: true
                                from: 10; to: 100; stepSize: 1
                                value: settingsBackend ? settingsBackend.brightness : 100
                                onMoved: if (settingsBackend)
                                    settingsBackend.previewBrightness(Math.round(value))
                                onPressedChanged: if (!pressed && settingsBackend)
                                    settingsBackend.setBrightness(Math.round(value))
                                background: Rectangle {
                                    x: brSlider.leftPadding
                                    y: brSlider.topPadding
                                       + brSlider.availableHeight / 2 - height / 2
                                    width: brSlider.availableWidth; height: 8
                                    radius: 4; color: "#33FFFFFF"
                                    Rectangle {
                                        width: brSlider.visualPosition * parent.width
                                        height: parent.height; radius: 4; color: "#FFD280"
                                    }
                                }
                                handle: Rectangle {
                                    x: brSlider.leftPadding + brSlider.visualPosition
                                       * (brSlider.availableWidth - width)
                                    y: brSlider.topPadding
                                       + brSlider.availableHeight / 2 - height / 2
                                    width: 30; height: 30; radius: 15
                                    color: brSlider.pressed ? "#FFE7B0" : "#FFD280"
                                    border.color: "#80FFFFFF"; border.width: 1
                                }
                            }
                            Rectangle {
                                Layout.preferredWidth: 44; Layout.preferredHeight: 40
                                radius: 8; color: brUp.pressed ? "#33FFD280" : "#15FFD280"
                                border.color: "#66FFD280"; border.width: 1
                                Text { anchors.centerIn: parent; text: "+"
                                       color: "#FFD280"; font.pixelSize: 20; font.bold: true }
                                MouseArea { id: brUp; anchors.fill: parent
                                    onClicked: if (settingsBackend)
                                        settingsBackend.setBrightness(
                                            Math.min(100, settingsBackend.brightness + 10)) }
                            }
                            Text {
                                Layout.preferredWidth: 52
                                text: (settingsBackend ? settingsBackend.brightness : 100)
                                      + " %"
                                color: "#FFD280"; font.pixelSize: 15; font.bold: true
                                horizontalAlignment: Text.AlignRight
                            }
                            }
                        }
                    }
                    // 시스템
                    ColumnLayout {
                        Layout.fillWidth: true; Layout.fillHeight: false
                        Layout.preferredHeight: 95
                        Layout.minimumHeight: 95
                        spacing: 4
                        Text { text: "시스템"; color: "#FF8080"
                               font.pixelSize: 15; font.bold: true }
                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            color: "transparent"; radius: 8
                            border.color: "#4DFF4646"; border.width: 1
                            RowLayout {
                            anchors.fill: parent; anchors.margins: 8
                            Text { text: "프로그램 종료"; color: "#FF8080"
                                   font.pixelSize: 14; font.bold: true }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredWidth: 150; Layout.preferredHeight: 45
                                radius: 8; color: exMa.pressed ? "#C83232" : "#26FF4646"
                                border.color: "#FF4646"; border.width: 2
                                Text { anchors.centerIn: parent; text: "종료"
                                       color: "#FF4646"; font.pixelSize: 15; font.bold: true }
                                MouseArea { id: exMa; anchors.fill: parent
                                    onClicked: if (settingsBackend) settingsBackend.exitClicked() }
                            }
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                    Text { Layout.alignment: Qt.AlignRight
                           text: "HMI System v1.3.2 | Build 2026.02.05"
                           color: "#4DFFFFFF"; font.pixelSize: 12 }
                }
            }

            // ---------- [1] IO 설정 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    Text { Layout.alignment: Qt.AlignRight
                           text: "※ 변경 후 [IO 설정 적용] 버튼을 눌러야 저장됩니다."
                           color: "#80FFFFFF"; font.pixelSize: 13 }
                    RowLayout {
                        Layout.fillWidth: true; Layout.preferredHeight: 42; spacing: 8
                        Text { text: "입력 그룹"; color: "#64FFDA"; font.pixelSize: 14; font.bold: true
                               Layout.preferredWidth: 74 }
                        Repeater {
                            model: settingsBackend ? settingsBackend.inputGroupLabels : []
                            delegate: Rectangle {
                                Layout.preferredWidth: 164; Layout.preferredHeight: 38
                                radius: 7; color: inGroupEdit.pressed ? "#284B63" : "#183544"
                                border.color: "#39758B"; border.width: 1
                                Text { anchors.left: parent.left; anchors.leftMargin: 10
                                       anchors.right: inGroupDelete.left; anchors.rightMargin: 4
                                       anchors.verticalCenter: parent.verticalCenter
                                       text: modelData; color: "white"; font.pixelSize: 12; font.bold: true
                                       elide: Text.ElideRight }
                                MouseArea { id: inGroupEdit; anchors.fill: parent; anchors.rightMargin: 34
                                    onClicked: settingsBackend.editIoGroup(true, index) }
                                Rectangle {
                                    id: inGroupDelete; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                    anchors.rightMargin: 5; width: 28; height: 28; radius: 5
                                    color: inDeleteMa.pressed ? "#A93226" : "#613036"
                                    Text { anchors.centerIn: parent; text: "×"; color: "#FFB3B3"; font.pixelSize: 18 }
                                    MouseArea { id: inDeleteMa; anchors.fill: parent
                                        onClicked: settingsBackend.removeIoGroup(true, index) }
                                }
                            }
                        }
                        Rectangle {
                            visible: settingsBackend ? settingsBackend.canAddInputGroup : false
                            Layout.preferredWidth: 40; Layout.preferredHeight: 38; radius: 7
                            color: inAddMa.pressed ? "#246B58" : "#174D41"; border.color: "#35A98B"
                            Text { anchors.centerIn: parent; text: "+"; color: "#64FFDA"; font.pixelSize: 24 }
                            MouseArea { id: inAddMa; anchors.fill: parent
                                onClicked: settingsBackend.addIoGroup(true) }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {
                        Layout.fillWidth: true; Layout.preferredHeight: 42; spacing: 8
                        Text { text: "출력 그룹"; color: "#FFD280"; font.pixelSize: 14; font.bold: true
                               Layout.preferredWidth: 74 }
                        Repeater {
                            model: settingsBackend ? settingsBackend.outputGroupLabels : []
                            delegate: Rectangle {
                                Layout.preferredWidth: 164; Layout.preferredHeight: 38
                                radius: 7; color: outGroupEdit.pressed ? "#5A4924" : "#3E321B"
                                border.color: "#8D7135"; border.width: 1
                                Text { anchors.left: parent.left; anchors.leftMargin: 10
                                       anchors.right: outGroupDelete.left; anchors.rightMargin: 4
                                       anchors.verticalCenter: parent.verticalCenter
                                       text: modelData; color: "white"; font.pixelSize: 12; font.bold: true
                                       elide: Text.ElideRight }
                                MouseArea { id: outGroupEdit; anchors.fill: parent; anchors.rightMargin: 34
                                    onClicked: settingsBackend.editIoGroup(false, index) }
                                Rectangle {
                                    id: outGroupDelete; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                    anchors.rightMargin: 5; width: 28; height: 28; radius: 5
                                    color: outDeleteMa.pressed ? "#A93226" : "#613036"
                                    Text { anchors.centerIn: parent; text: "×"; color: "#FFB3B3"; font.pixelSize: 18 }
                                    MouseArea { id: outDeleteMa; anchors.fill: parent
                                        onClicked: settingsBackend.removeIoGroup(false, index) }
                                }
                            }
                        }
                        Rectangle {
                            visible: settingsBackend ? settingsBackend.canAddOutputGroup : false
                            Layout.preferredWidth: 40; Layout.preferredHeight: 38; radius: 7
                            color: outAddMa.pressed ? "#735D25" : "#51431F"; border.color: "#A88738"
                            Text { anchors.centerIn: parent; text: "+"; color: "#FFD280"; font.pixelSize: 24 }
                            MouseArea { id: outAddMa; anchors.fill: parent
                                onClicked: settingsBackend.addIoGroup(false) }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 0
                        Text { text: "  입력 (Input) 이름"; color: "#AAAAAA"
                               font.pixelSize: 13; font.bold: true; Layout.fillWidth: true }
                        Text { text: "  출력 (Output) 이름 / 자동정지 동작"; color: "#AAAAAA"
                               font.pixelSize: 13; font.bold: true; Layout.fillWidth: true }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: "#26000000"; radius: 12
                        ListView {
                            anchors.fill: parent; anchors.margins: 6
                            clip: true; model: ioModel; spacing: 6
                            cacheBuffer: 2000
                            boundsBehavior: Flickable.StopAtBounds
                            delegate: RowLayout {
                                width: ListView.view ? ListView.view.width : 0
                                height: 44; spacing: 8
                                Text { visible: model.inhas; text: model.xaddr; color: "#64FFDA"
                                       font.pixelSize: 15; font.bold: true
                                       Layout.preferredWidth: 44
                                       horizontalAlignment: Text.AlignHCenter }
                                Rectangle {
                                    visible: model.inhas
                                    Layout.fillWidth: true; Layout.preferredHeight: 38
                                    radius: 6; color: inMa.pressed ? "#33468CFF" : "#1AFFFFFF"
                                    border.color: "#33FFFFFF"; border.width: 1
                                    Text { anchors.fill: parent; anchors.leftMargin: 10
                                           verticalAlignment: Text.AlignVCenter
                                           text: model.inname; color: "white"
                                           font.pixelSize: 14; elide: Text.ElideRight }
                                    MouseArea { id: inMa; anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.editInName(model.inindex) }
                                }
                                Item { visible: !model.inhas; Layout.preferredWidth: 44 }
                                Item { visible: !model.inhas; Layout.fillWidth: true; Layout.preferredHeight: 38 }
                                Text { visible: model.outhas; text: model.yaddr; color: "#FFD280"
                                       font.pixelSize: 15; font.bold: true
                                       Layout.preferredWidth: 44
                                       horizontalAlignment: Text.AlignHCenter }
                                Rectangle {
                                    visible: model.outhas
                                    Layout.fillWidth: true; Layout.preferredHeight: 38
                                    radius: 6; color: ouMa.pressed ? "#33468CFF" : "#1AFFFFFF"
                                    border.color: "#33FFFFFF"; border.width: 1
                                    Text { anchors.left: parent.left; anchors.right: outModeButton.left
                                           anchors.top: parent.top; anchors.bottom: parent.bottom
                                           anchors.leftMargin: 10; anchors.rightMargin: 6
                                           verticalAlignment: Text.AlignVCenter
                                           text: model.outname; color: "white"
                                           font.pixelSize: 14; elide: Text.ElideRight }
                                    MouseArea { id: ouMa; anchors.fill: parent; anchors.rightMargin: 82
                                        onClicked: if (settingsBackend)
                                            settingsBackend.editOutName(model.outindex) }
                                    Rectangle {
                                        id: outModeButton
                                        anchors.right: parent.right; anchors.rightMargin: 3
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 76; height: 32; radius: 5
                                        color: model.outmode === "LATCH"
                                               ? (outModeMa.pressed ? "#146E64" : "#18594F")
                                               : (outModeMa.pressed ? "#9B3B35" : "#71332F")
                                        border.width: 1
                                        border.color: model.outmode === "LATCH" ? "#45D6C2" : "#E06B62"
                                        Text {
                                            anchors.centerIn: parent
                                            text: model.outmode
                                            color: "white"; font.pixelSize: 12; font.bold: true
                                        }
                                        MouseArea { id: outModeMa; anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.toggleOutputStopMode(model.outindex) }
                                    }
                                }
                                Item { visible: !model.outhas; Layout.preferredWidth: 44 }
                                Item { visible: !model.outhas; Layout.fillWidth: true; Layout.preferredHeight: 38 }
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 50
                        Layout.fillHeight: false; radius: 10
                        color: ioSaveMa.pressed ? "#2A65C7" : "#468CFF"
                        Text { anchors.centerIn: parent; text: "IO 설정 적용"
                               color: "white"; font.pixelSize: 16; font.bold: true }
                        MouseArea { id: ioSaveMa; anchors.fill: parent
                            onClicked: if (settingsBackend) settingsBackend.applyIoNames() }
                    }
                }
            }

            // ---------- [2] 시스템 파라미터 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredWidth: 150; Layout.preferredHeight: 40
                            radius: 6; color: pApply.pressed ? "#E74C3C" : "#C0392B"
                            border.color: "#E74C3C"; border.width: 1
                            Text { anchors.centerIn: parent; text: "파라미터 적용"
                                   color: "white"; font.pixelSize: 13; font.bold: true }
                            MouseArea { id: pApply; anchors.fill: parent
                                onClicked: if (settingsBackend) settingsBackend.saveParams() }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: "#26000000"; radius: 10
                        Flickable {
                            anchors.fill: parent; anchors.margins: 10
                            clip: true; contentHeight: paramCol.height
                            boundsBehavior: Flickable.StopAtBounds
                            ColumnLayout {
                                id: paramCol
                                width: parent.width; spacing: 14
                                Text { text: "축 구성 및 모션 설정 (DT15000 ~)"
                                       color: "#FFD700"; font.pixelSize: 14; font.bold: true }
                                // 헤더
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 8
                                    Repeater {
                                        model: ["축","사용","엔코더","방향","스트로크","가감속","PPR"]
                                        delegate: Text { text: modelData; color: "#BBBBBB"
                                            font.pixelSize: 12; font.bold: true
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 1
                                            horizontalAlignment: Text.AlignHCenter }
                                    }
                                }
                                Repeater {
                                    model: paramModel
                                    delegate: RowLayout {
                                        Layout.fillWidth: true; spacing: 8; height: 44
                                        Text { text: model.axname; color: "white"
                                            font.pixelSize: 14; font.bold: true
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 1
                                            horizontalAlignment: Text.AlignHCenter }
                                        // 사용
                                        Item { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            Rectangle { anchors.centerIn: parent
                                                width: 26; height: 26; radius: 4
                                                color: model.axuse ? "#468CFF" : "transparent"
                                                border.color: model.axuse ? "#468CFF" : "#888888"
                                                border.width: 2
                                                Text { anchors.centerIn: parent
                                                    text: model.axuse ? "✓" : ""
                                                    color: "white"; font.pixelSize: 16; font.bold: true }
                                                MouseArea { anchors.fill: parent
                                                    onClicked: if (settingsBackend)
                                                        settingsBackend.toggleAxisUse(index) } } }
                                        // 엔코더 분류 (앱 설정 — PLC 파라미터 주소를 사용하지 않음)
                                        Item { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            Rectangle { anchors.centerIn: parent
                                                width: 100; height: 30; radius: 4
                                                property bool absolute:
                                                    model.axencoder === "absolute"
                                                color: absolute ? "#332E86C1" : "#33AF601A"
                                                border.color: absolute ? "#5DADE2" : "#F5B041"
                                                border.width: 1
                                                Text { anchors.centerIn: parent
                                                    text: parent.absolute ? "앱솔루트" : "인크리멘탈"
                                                    color: parent.absolute ? "#85C1E9" : "#F8C471"
                                                    font.pixelSize: 11; font.bold: true }
                                                MouseArea { anchors.fill: parent
                                                    onClicked: if (settingsBackend)
                                                        settingsBackend.toggleAxisEncoder(index) } } }
                                        // 방향
                                        Item { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            Rectangle { anchors.centerIn: parent
                                                width: 90; height: 30; radius: 4
                                                property bool fwd: model.axdir === 0
                                                color: fwd ? "#334CC600" : "#33FF6400"
                                                border.color: fwd ? "#00FF00" : "#FF8000"
                                                border.width: 1
                                                Text { anchors.centerIn: parent
                                                    text: parent.fwd ? "정방향" : "역방향"
                                                    color: parent.fwd ? "#00FF00" : "#FF8000"
                                                    font.pixelSize: 12; font.bold: true }
                                                MouseArea { anchors.fill: parent
                                                    onClicked: if (settingsBackend)
                                                        settingsBackend.toggleAxisDir(index) } } }
                                        // 스트로크
                                        Rectangle { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            radius: 4; color: "#1AFFFFFF"
                                            border.color: "#33FFFFFF"; border.width: 1
                                            Text { anchors.centerIn: parent; text: model.axstroke
                                                color: "#FFD280"; font.pixelSize: 13; font.bold: true }
                                            MouseArea { anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.editStroke(index) } }
                                        // 가감속
                                        Rectangle { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            radius: 4; color: "#1AFFFFFF"
                                            border.color: "#33FFFFFF"; border.width: 1
                                            Text { anchors.centerIn: parent; text: model.axaccel
                                                color: "white"; font.pixelSize: 13; font.bold: true }
                                            MouseArea { anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.editAccel(index) } }
                                        // PPR
                                        Rectangle { Layout.fillWidth: true
                                            Layout.preferredWidth: 1; height: 36
                                            radius: 4; color: "#1AFFFFFF"
                                            border.color: "#33FFFFFF"; border.width: 1
                                            Text { anchors.centerIn: parent; text: model.axppr
                                                color: "white"; font.pixelSize: 13; font.bold: true }
                                            MouseArea { anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.editPpr(index) } }
                                    }
                                }
                                Rectangle { Layout.fillWidth: true; height: 1
                                            color: "#22FFFFFF" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "JOG 모드"; color: "#DDDDDD"
                                           font.pixelSize: 13; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        Layout.preferredWidth: 100; Layout.preferredHeight: 38
                                        radius: 8
                                        property bool on: settingsBackend
                                            ? settingsBackend.homeOn : false
                                        color: on ? "#334CC864" : "#14FFFFFF"
                                        border.color: on ? "#00CC66" : "#666666"
                                        border.width: 1
                                        Text { anchors.centerIn: parent
                                            text: parent.on ? "ON" : "OFF"
                                            color: parent.on ? "#00CC66" : "#AAAAAA"
                                            font.pixelSize: 15; font.bold: true }
                                        MouseArea { anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.toggleHome() }
                                    }
                                }
                                Text { text: "데이터셋 (Zero Preset) — 버튼을 누르면 해당 축 원점 설정 (DT50033)"
                                       color: "#DDDDDD"; font.pixelSize: 12 }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4; rowSpacing: 8; columnSpacing: 8
                                    Repeater {
                                        model: paramModel
                                        delegate: Rectangle {
                                            Layout.fillWidth: true; Layout.preferredHeight: 50
                                            radius: 6
                                            color: dsMa.pressed ? "#E67E22" : "#444444"
                                            border.color: dsMa.pressed ? "#D35400" : "#666666"
                                            border.width: 1
                                            Text { anchors.centerIn: parent
                                                text: model.axname + "\nSET"
                                                horizontalAlignment: Text.AlignHCenter
                                                color: dsMa.pressed ? "white" : "#AAAAAA"
                                                font.pixelSize: 12; font.bold: true }
                                            MouseArea { id: dsMa; anchors.fill: parent
                                                onPressed: if (settingsBackend)
                                                    settingsBackend.datasetPressed(index)
                                                onReleased: if (settingsBackend)
                                                    settingsBackend.datasetReleased(index) }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ---------- [3] 밸브 설정 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredWidth: 120; Layout.preferredHeight: 40
                            radius: 6; color: vSave.pressed ? "#1E8449" : "#27AE60"
                            border.color: "#2ECC71"; border.width: 1
                            Text { anchors.centerIn: parent; text: " 저장"
                                   color: "white"; font.pixelSize: 13; font.bold: true }
                            MouseArea { id: vSave; anchors.fill: parent
                                onClicked: if (settingsBackend) settingsBackend.saveValveConfig() }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: "#26000000"; radius: 10
                        // 헤더+리스트를 같은 ColumnLayout·같은 인셋에 둬 컬럼 픽셀정렬 보장.
                        // 컬럼폭: 사용50 / 번호55 / 이름(유동) / 동작110 / 순서76 / JOG96
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 6; spacing: 6
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: false
                                Layout.preferredHeight: 22
                                spacing: 8
                                Text { text: "사용"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.preferredWidth: 50
                                    horizontalAlignment: Text.AlignHCenter }
                                Text { text: "번호"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.preferredWidth: 55
                                    horizontalAlignment: Text.AlignHCenter }
                                Text { text: "이름"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.fillWidth: true
                                    horizontalAlignment: Text.AlignHCenter }
                                Text { text: "동작"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.preferredWidth: 110
                                    horizontalAlignment: Text.AlignHCenter }
                                Text { text: "순서"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.preferredWidth: 76
                                    horizontalAlignment: Text.AlignHCenter }
                                Text { text: "JOG"; color: "#FFD700"; font.pixelSize: 12
                                    font.bold: true; Layout.preferredWidth: 96
                                    horizontalAlignment: Text.AlignHCenter }
                            }
                            ListView {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                clip: true; model: valveModel; spacing: 6
                                cacheBuffer: 2400
                                boundsBehavior: Flickable.StopAtBounds
                                delegate: RowLayout {
                                    width: ListView.view ? ListView.view.width : 0
                                    height: 42; spacing: 8
                                    // 사용
                                    Item { Layout.preferredWidth: 50; height: 40
                                        Rectangle { anchors.centerIn: parent
                                            width: 24; height: 24; radius: 4
                                            color: model.venabled ? "#468CFF" : "transparent"
                                            border.color: model.venabled ? "#468CFF" : "#888888"
                                            border.width: 2
                                            Text { anchors.centerIn: parent
                                                text: model.venabled ? "✓" : ""
                                                color: "white"; font.pixelSize: 15; font.bold: true }
                                            MouseArea { anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.toggleValveEnabled(index) } } }
                                    Text { text: model.vyaddr; color: "#FFD280"
                                        font.pixelSize: 12; font.bold: true
                                        Layout.preferredWidth: 55
                                        horizontalAlignment: Text.AlignHCenter }
                                    Rectangle { Layout.fillWidth: true; height: 35
                                        radius: 4
                                        color: vnMa.pressed ? "#33468CFF" : "#1AFFFFFF"
                                        border.color: "#666666"; border.width: 1
                                        Text { anchors.fill: parent; anchors.leftMargin: 10
                                            verticalAlignment: Text.AlignVCenter
                                            text: model.vname; color: "white"
                                            font.pixelSize: 12; elide: Text.ElideRight }
                                        MouseArea { id: vnMa; anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.editValveName(index) } }
                                    Rectangle { Layout.preferredWidth: 110; height: 35
                                        radius: 4
                                        property bool tg: model.vtoggle
                                        color: tg ? "#332ECC71" : "#33468CFF"
                                        border.color: tg ? "#2ECC71" : "#468CFF"
                                        border.width: 1
                                        Text { anchors.centerIn: parent
                                            text: parent.tg ? "Toggle" : "Momentary"
                                            color: parent.tg ? "#2ECC71" : "white"
                                            font.pixelSize: 11; font.bold: true }
                                        MouseArea { anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.toggleValveMode(index) } }
                                    RowLayout { Layout.preferredWidth: 76
                                        Layout.fillWidth: false; spacing: 3
                                        Rectangle { Layout.fillWidth: true; height: 30
                                            radius: 4; color: vuMa.pressed ? "#33468CFF" : "#1AFFFFFF"
                                            border.color: "#666666"; border.width: 1
                                            Text { anchors.centerIn: parent; text: "▲"
                                                color: "white"; font.pixelSize: 10 }
                                            MouseArea { id: vuMa; anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.moveValveUp(index) } }
                                        Rectangle { Layout.fillWidth: true; height: 30
                                            radius: 4; color: vdMa.pressed ? "#33468CFF" : "#1AFFFFFF"
                                            border.color: "#666666"; border.width: 1
                                            Text { anchors.centerIn: parent; text: "▼"
                                                color: "white"; font.pixelSize: 10 }
                                            MouseArea { id: vdMa; anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.moveValveDown(index) } } }
                                    RowLayout { Layout.preferredWidth: 96
                                        Layout.fillWidth: false; spacing: 3
                                        Rectangle { Layout.fillWidth: true; height: 33
                                            radius: 4
                                            property bool j: model.vjog
                                            color: j ? "#3300E5FF" : "#12FFFFFF"
                                            border.color: j ? "#00E5FF" : "#555555"
                                            border.width: 1
                                            Text { anchors.centerIn: parent; text: "JOG"
                                                color: parent.j ? "#00E5FF" : "#666666"
                                                font.pixelSize: 11; font.bold: true }
                                            MouseArea { anchors.fill: parent
                                                onClicked: if (settingsBackend)
                                                    settingsBackend.toggleValveJog(index) } }
                                        ColumnLayout { spacing: 1
                                            Rectangle { Layout.preferredWidth: 22
                                                Layout.preferredHeight: 15; radius: 3
                                                color: "#0DFFFFFF"
                                                border.color: model.vjog ? "#00B4D8" : "#444444"
                                                border.width: 1
                                                Text { anchors.centerIn: parent; text: "▲"
                                                    color: model.vjog ? "#00B4D8" : "#555555"
                                                    font.pixelSize: 8 }
                                                MouseArea { anchors.fill: parent
                                                    enabled: model.vjog
                                                    onClicked: if (settingsBackend)
                                                        settingsBackend.jogOrderUp(index) } }
                                            Rectangle { Layout.preferredWidth: 22
                                                Layout.preferredHeight: 15; radius: 3
                                                color: "#0DFFFFFF"
                                                border.color: model.vjog ? "#00B4D8" : "#444444"
                                                border.width: 1
                                                Text { anchors.centerIn: parent; text: "▼"
                                                    color: model.vjog ? "#00B4D8" : "#555555"
                                                    font.pixelSize: 8 }
                                                MouseArea { anchors.fill: parent
                                                    enabled: model.vjog
                                                    onClicked: if (settingsBackend)
                                                        settingsBackend.jogOrderDown(index) } } }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ---------- [4] 알람 메시지 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            Layout.preferredWidth: 140; Layout.preferredHeight: 40
                            radius: 6; color: aAdd.pressed ? "#33468CFF" : "#26468CFF"
                            border.color: "#468CFF"; border.width: 1
                            Text { anchors.centerIn: parent; text: "＋ 알람 추가"
                                   color: "#468CFF"; font.pixelSize: 13; font.bold: true }
                            MouseArea { id: aAdd; anchors.fill: parent
                                onClicked: if (settingsBackend) settingsBackend.addAlarm() }
                        }
                        Rectangle {
                            Layout.preferredWidth: 100; Layout.preferredHeight: 40
                            radius: 6; color: aSave.pressed ? "#1A4FA0" : "#2A65C7"
                            border.color: "#468CFF"; border.width: 1
                            Text { anchors.centerIn: parent; text: "저장"
                                   color: "white"; font.pixelSize: 13; font.bold: true }
                            MouseArea { id: aSave; anchors.fill: parent
                                onClicked: if (settingsBackend) settingsBackend.saveAlarms() }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: "#26000000"; radius: 8
                        ListView {
                            anchors.fill: parent; anchors.margins: 6
                            clip: true; model: alarmModel; spacing: 4
                            cacheBuffer: 1600
                            boundsBehavior: Flickable.StopAtBounds
                            delegate: Rectangle {
                                width: ListView.view ? ListView.view.width : 0
                                height: 48; radius: 6; color: "#0AFFFFFF"
                                RowLayout {
                                    anchors.fill: parent; anchors.margins: 8; spacing: 8
                                    Text { text: model.ano; color: "#FF6B6B"
                                        font.pixelSize: 14; font.bold: true
                                        Layout.preferredWidth: 60
                                        horizontalAlignment: Text.AlignHCenter }
                                    Text { text: model.amsg; color: "white"
                                        font.pixelSize: 14; Layout.fillWidth: true
                                        elide: Text.ElideRight }
                                    Rectangle { Layout.preferredWidth: 70
                                        Layout.preferredHeight: 34; radius: 4
                                        color: aeMa.pressed ? "#33FFFFFF" : "#1AFFFFFF"
                                        border.color: "#888888"; border.width: 1
                                        Text { anchors.centerIn: parent; text: "수정"
                                            color: "white"; font.pixelSize: 13; font.bold: true }
                                        MouseArea { id: aeMa; anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.editAlarm(model.anoraw) } }
                                    Rectangle { Layout.preferredWidth: 70
                                        Layout.preferredHeight: 34; radius: 4
                                        color: adMa.pressed ? "#33FF4646" : "#26FF4646"
                                        border.color: "#FF4646"; border.width: 1
                                        Text { anchors.centerIn: parent; text: "삭제"
                                            color: "#FF4646"; font.pixelSize: 13; font.bold: true }
                                        MouseArea { id: adMa; anchors.fill: parent
                                            onClicked: if (settingsBackend)
                                                settingsBackend.deleteAlarm(model.anoraw) } }
                                }
                            }
                        }
                    }
                }
            }

            // ---------- [5] 인터록 설정 ----------
            Item {
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 16
                    Text { text: "모드 인터록 설정"; color: "#00E5FF"
                           font.pixelSize: 18; font.bold: true }
                    Text {
                        Layout.fillWidth: true
                        text: "• 배타(⊗): 같은 그룹에서 하나를 켜면 나머지가 자동으로 꺼집니다.\n"
                            + "• 필수(★): 같은 그룹에서 마지막 하나는 끌 수 없습니다.\n"
                            + "• 두 옵션은 독립적으로 설정할 수 있습니다."
                        color: "#9CA3AF"; font.pixelSize: 14; wrapMode: Text.WordWrap
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#374151" }
                    Rectangle {
                        Layout.fillWidth: true; Layout.preferredHeight: 55; radius: 10
                        color: ilMa.pressed ? "#3300E5FF" : "#1A00E5FF"
                        border.color: "#00E5FF"; border.width: 2
                        Text { anchors.centerIn: parent; text: "인터록 그룹 설정 열기"
                               color: "#00E5FF"; font.pixelSize: 17; font.bold: true }
                        MouseArea { id: ilMa; anchors.fill: parent
                            onClicked: if (settingsBackend) settingsBackend.openInterlock() }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // ---------- [6] 네트워크 ----------
            Item {
                Flickable {
                    anchors.fill: parent; anchors.margins: 10
                    clip: true; contentHeight: netCol.height
                    boundsBehavior: Flickable.StopAtBounds
                    ColumnLayout {
                        id: netCol
                        width: parent.width; spacing: 14

                        Text { text: "무선 (WiFi)"; color: "#DDDDDD"
                               font.pixelSize: 15; font.bold: true }
                        GridLayout {
                            Layout.fillWidth: true; columns: 4
                            rowSpacing: 6; columnSpacing: 12
                            Text { text: "SSID:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.wSsid : "-"
                                   color: "#00E5FF"; font.pixelSize: 14; font.bold: true
                                   Layout.fillWidth: true }
                            Text { text: "신호:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.wSignal : "-"
                                   color: "#DDDDDD"; font.pixelSize: 14; Layout.fillWidth: true }
                            Text { text: "IP 주소:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.wIp : "-"
                                   color: "#FFD280"; font.pixelSize: 14; font.bold: true
                                   Layout.fillWidth: true }
                            Text { text: "인터페이스:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.wIface : "-"
                                   color: "#AAAAAA"; font.pixelSize: 14; Layout.fillWidth: true }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Repeater {
                                model: [["새로고침","refreshWifi"],["네트워크 스캔","scanWifi"]]
                                delegate: Rectangle {
                                    Layout.preferredWidth: 130; Layout.preferredHeight: 38
                                    radius: 6; color: wbMa.pressed ? "#33468CFF" : "#2E468CFF"
                                    border.color: "#99468CFF"; border.width: 1
                                    Text { anchors.centerIn: parent; text: modelData[0]
                                        color: "#DDEEFF"; font.pixelSize: 14; font.bold: true }
                                    MouseArea { id: wbMa; anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.wifiBtn(modelData[1]) }
                                }
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredWidth: 110; Layout.preferredHeight: 38
                                radius: 6; color: wDis.pressed ? "#33FF4646" : "#26FF4646"
                                border.color: "#80FF4646"; border.width: 1
                                Text { anchors.centerIn: parent
                                    text: settingsBackend ? settingsBackend.wToggleText : "연결"
                                    color: "#FFCCCC"; font.pixelSize: 14; font.bold: true }
                                MouseArea { id: wDis; anchors.fill: parent
                                    onClicked: if (settingsBackend)
                                        settingsBackend.wifiBtn("toggleWifi") }
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 220
                            color: "#40000000"; radius: 8
                            border.color: "#1FFFFFFF"; border.width: 1
                            ListView {
                                anchors.fill: parent; anchors.margins: 4
                                clip: true; model: wifiModel; spacing: 0
                                boundsBehavior: Flickable.StopAtBounds
                                delegate: Rectangle {
                                    width: ListView.view ? ListView.view.width : 0
                                    height: 42
                                    color: wiMa.pressed ? "#33468CFF" : "transparent"
                                    Text { anchors.verticalCenter: parent.verticalCenter
                                        x: 12; text: model.wtext; color: "#EEEEEE"
                                        font.pixelSize: 15 }
                                    Rectangle { anchors.bottom: parent.bottom
                                        width: parent.width; height: 1; color: "#0DFFFFFF" }
                                    MouseArea { id: wiMa; anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.wifiItemActivated(index) }
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: "#22FFFFFF" }
                        Text { text: "유선 (Ethernet)"; color: "#FFD280"
                               font.pixelSize: 15; font.bold: true }
                        GridLayout {
                            Layout.fillWidth: true; columns: 4
                            rowSpacing: 6; columnSpacing: 12
                            Text { text: "인터페이스:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eIface : "-"
                                   color: "#FFD280"; font.pixelSize: 14; font.bold: true
                                   Layout.fillWidth: true }
                            Text { text: "상태:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eState : "-"
                                   color: settingsBackend ? settingsBackend.eStateColor : "#DDD"
                                   font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                            Text { text: "IP 주소:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eIp : "-"
                                   color: "#00E5FF"; font.pixelSize: 14; font.bold: true
                                   Layout.fillWidth: true }
                            Text { text: "방식:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eMethod : "-"
                                   color: "#DDDDDD"; font.pixelSize: 14; Layout.fillWidth: true }
                            Text { text: "게이트웨이:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eGw : "-"
                                   color: "#DDDDDD"; font.pixelSize: 14; Layout.fillWidth: true }
                            Text { text: "프로파일:"; color: "#DDDDDD"; font.pixelSize: 14 }
                            Text { text: settingsBackend ? settingsBackend.eConn : "-"
                                   color: "#AAAAAA"; font.pixelSize: 14; Layout.fillWidth: true }
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Text { text: "인터넷 우선:"; color: "#DDDDDD"
                                   font.pixelSize: 14 }
                            Repeater {
                                model: [["무선(WiFi)","wifi","prioWifi"],
                                        ["유선(Ethernet)","eth","prioEth"]]
                                delegate: Rectangle {
                                    Layout.preferredWidth: 140; Layout.preferredHeight: 38
                                    radius: 6
                                    property bool sel: settingsBackend
                                        && settingsBackend.netPriority === modelData[1]
                                    color: sel ? "#3346D17A"
                                        : (npMa.pressed ? "#33468CFF" : "#2E468CFF")
                                    border.width: 1
                                    border.color: sel ? "#CC46D17A" : "#99468CFF"
                                    Text { anchors.centerIn: parent; text: modelData[0]
                                        color: sel ? "#CFFFE0" : "#DDEEFF"
                                        font.pixelSize: 14; font.bold: true }
                                    MouseArea { id: npMa; anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.wifiBtn(modelData[2]) }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "무선 우선: 인터넷=WiFi, PLC=유선(eth0) 고정 · " +
                                  "유선 우선: 인터넷·통신 모두 eth0"
                            color: "#999999"; font.pixelSize: 12
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true; spacing: 10
                            Repeater {
                                model: [["새로고침","refreshEth"],["DHCP 사용","ethDhcp"],
                                        ["고정 IP 설정","ethStatic"]]
                                delegate: Rectangle {
                                    Layout.preferredWidth: 130; Layout.preferredHeight: 38
                                    radius: 6; color: ebMa.pressed ? "#33468CFF" : "#2E468CFF"
                                    border.color: "#99468CFF"; border.width: 1
                                    Text { anchors.centerIn: parent; text: modelData[0]
                                        color: "#DDEEFF"; font.pixelSize: 14; font.bold: true }
                                    MouseArea { id: ebMa; anchors.fill: parent
                                        onClicked: if (settingsBackend)
                                            settingsBackend.wifiBtn(modelData[1]) }
                                }
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Item { Layout.preferredHeight: 10 }
                    }
                }
            }
        }
    }

    // ===== 인터록 그룹 설정 오버레이 (별도 윈도우 X — 같은 씬 내 풀스크린) =====
    Rectangle {
        id: ilOverlay
        anchors.fill: parent
        color: "#111827"
        visible: settingsBackend ? settingsBackend.ilOpen : false
        MouseArea { anchors.fill: parent }   // 뒤 입력 차단

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 8

            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: false
                Layout.preferredHeight: 40
                Text { text: "인터록 그룹 설정"; color: "#00E5FF"
                       font.pixelSize: 20; font.bold: true }
                Item { Layout.fillWidth: true }
                Rectangle {
                    Layout.preferredWidth: 110; Layout.preferredHeight: 34
                    radius: 6; color: ilClr.pressed ? "#66FF4646" : "#33FF4646"
                    border.color: "#FF4646"; border.width: 1
                    Text { anchors.centerIn: parent; text: "전체 해제"
                           color: "#FF4646"; font.pixelSize: 13; font.bold: true }
                    MouseArea { id: ilClr; anchors.fill: parent
                        onClicked: if (settingsBackend) settingsBackend.ilClear() }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#374151" }

            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: false
                Layout.preferredHeight: 96; spacing: 8
                Repeater {
                    model: ilGroupModel
                    delegate: Rectangle {
                        Layout.preferredWidth: 112; Layout.fillHeight: true
                        radius: 8; color: model.gcardbg
                        border.color: model.gcardborder; border.width: 1
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 6; spacing: 4
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 24
                                radius: 5; color: model.glabelbg
                                Text { anchors.centerIn: parent; text: model.glabel
                                       color: "white"; font.pixelSize: 15; font.bold: true }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 30
                                radius: 5; color: model.exbg
                                border.color: model.exborder; border.width: model.exbw
                                Text { anchors.centerIn: parent; text: model.extext
                                       color: model.exfg; font.pixelSize: 12; font.bold: true }
                                MouseArea { anchors.fill: parent
                                    onClicked: if (settingsBackend)
                                        settingsBackend.ilToggleExcl(model.gnum) }
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.preferredHeight: 30
                                radius: 5; color: model.mnbg
                                border.color: model.mnborder; border.width: model.mnbw
                                Text { anchors.centerIn: parent; text: model.mntext
                                       color: model.mnfg; font.pixelSize: 12; font.bold: true }
                                MouseArea { anchors.fill: parent
                                    onClicked: if (settingsBackend)
                                        settingsBackend.ilToggleMand(model.gnum) }
                            }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }

            Text {
                Layout.fillWidth: true
                text: "모드 버튼을 탭하면 그룹 순환 (없음 → G1 → … → G8 → 없음).  "
                    + "배타: 하나 ON 시 나머지 자동 OFF.  필수: 마지막 하나는 끌 수 없음."
                color: "#9CA3AF"; font.pixelSize: 13; wrapMode: Text.WordWrap
            }

            GridView {
                id: ilGv
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; model: ilModeModel
                cacheBuffer: 2000
                boundsBehavior: Flickable.StopAtBounds
                cellWidth: Math.floor(width / 4)
                cellHeight: 76
                delegate: Item {
                    width: ilGv.cellWidth; height: ilGv.cellHeight
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 5
                        radius: 8; color: model.mbg
                        border.color: model.mborder; border.width: model.mbw
                        Text { anchors.centerIn: parent
                               horizontalAlignment: Text.AlignHCenter
                               text: model.mtext; color: model.mfg
                               font.pixelSize: 13; font.bold: true }
                        MouseArea { anchors.fill: parent
                            onClicked: if (settingsBackend)
                                settingsBackend.ilCycle(index) }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: false
                Layout.preferredHeight: 46; spacing: 10
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    radius: 8; color: ilCx.pressed ? "#33FFFFFF" : "#14FFFFFF"
                    border.color: "#555555"; border.width: 1
                    Text { anchors.centerIn: parent; text: "취소"
                           color: "#CCCCCC"; font.pixelSize: 16; font.bold: true }
                    MouseArea { id: ilCx; anchors.fill: parent
                        onClicked: if (settingsBackend) settingsBackend.ilReject() }
                }
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    radius: 8; color: ilOk.pressed ? "#5900E5FF" : "#2600E5FF"
                    border.color: "#00E5FF"; border.width: 1
                    Text { anchors.centerIn: parent; text: "저장"
                           color: "#00E5FF"; font.pixelSize: 16; font.bold: true }
                    MouseArea { id: ilOk; anchors.fill: parent
                        onClicked: if (settingsBackend) settingsBackend.ilAccept() }
                }
            }
        }
    }
}
