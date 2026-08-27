import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    objectName: "sequenceEditorSurface"
    required property var seqEditor
    required property var stepModel
    color: "#18232E"
    opacity: 1.0
    property color panel: "#202D3A"
    property color borderCol: "#35506A"
    property var axisNames: ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]
    property var datMathSymbols: ["+", "−", "×", "÷"]
    function stepColor(kind) {
        var colors = {"POS":"#468CFF", "WPOS":"#36B7C9", "OUT":"#FFA500", "IN":"#FF69B4",
                      "TMR":"#F1C40F", "JMP":"#00E5FF", "CALL":"#FF00FF",
                      "DAT":"#00FF9C", "END":"#FF4646", "COMMENT":"#FFD700"}
        return colors[kind] || "#71859A"
    }

    Connections {
        target: root.seqEditor
        function onStepMoved(row, direction) {
            // Twelve rows are visible. Center falls between rows 6 and 7:
            // upward movement anchors at row 7, downward at row 6.
            list.positionViewAtIndex(row, ListView.Center)
            // Apply the half-row correction synchronously. Deferring this to
            // the next event-loop turn renders one frame before the scroll and
            // makes the selected row appear to blink/jump.
            var halfSlot = list.height / 24
            var wanted = list.contentY + (direction < 0 ? -halfSlot : halfSlot)
            var minimum = list.originY
            var maximum = Math.max(minimum,
                                   list.originY + list.contentHeight - list.height)
            list.contentY = Math.max(minimum, Math.min(maximum, wanted))
        }
    }

    TimerCardPopup {
        id: timerCardPopup
        property string purpose: "step"
        items: !root.seqEditor ? []
               : purpose === "timeup" ? root.seqEditor.timeupTimerCards
               : purpose === "timeout" ? root.seqEditor.timeoutTimerCards
               : root.seqEditor.timerCards
        currentName: !root.seqEditor ? ""
                     : purpose === "timeup" ? root.seqEditor.selectedTimeupTimerName
                     : purpose === "timeout" ? root.seqEditor.selectedTimeoutTimerName
                     : root.seqEditor.selectedLibraryTimerName
        onSelected: function(name) {
            if (purpose === "timeup")
                root.seqEditor.selectTimeupTimer(name)
            else if (purpose === "timeout")
                root.seqEditor.selectTimeoutTimer(name)
            else
                root.seqEditor.selectLibraryTimer(name)
        }
        onRenameRequested: function(name) { root.seqEditor.renameLibraryTimer(name) }
    }

    VariableCardPopup {
        id: variableCardPopup
        property string purpose: "io_bit"
        kind: purpose === "io_bit" || purpose === "cond_bit" ? "bit" : "data"
        items: !root.seqEditor ? []
               : kind === "bit" ? root.seqEditor.bitCards : root.seqEditor.dataCards
        currentId: !root.seqEditor ? -1
                   : purpose === "io_bit" ? root.seqEditor.selectedIoBitId
                   : purpose === "cond_bit" ? root.seqEditor.selectedCondBitId
                   : purpose === "dat_data" ? root.seqEditor.selectedDatDataId
                   : purpose === "dat_left_data" ? root.seqEditor.selectedDatLeftDataId
                   : purpose === "dat_right_data" ? root.seqEditor.selectedDatRightDataId
                   : root.seqEditor.selectedCmpDataId
        titleText: purpose === "io_bit" ? "OUT / IN 내부비트 선택"
                   : purpose === "cond_bit" ? "JMP 조건 내부비트 선택"
                   : purpose === "dat_data" ? "DAT 결과 데이터 선택"
                   : purpose === "dat_left_data" ? "DAT 데이터 A 선택"
                   : purpose === "dat_right_data" ? "DAT 데이터 B 선택"
                   : "JMP 비교 데이터 선택"
        onSelected: function(itemId) {
            if (purpose === "io_bit")
                root.seqEditor.selectIoBit(itemId)
            else if (purpose === "cond_bit")
                root.seqEditor.selectCondBit(itemId)
            else if (purpose === "dat_data")
                root.seqEditor.selectDatData(itemId)
            else if (purpose === "dat_left_data")
                root.seqEditor.selectDatLeftData(itemId)
            else if (purpose === "dat_right_data")
                root.seqEditor.selectDatRightData(itemId)
            else
                root.seqEditor.selectCmpData(itemId)
        }
        onAddRequested: {
            if (kind === "bit")
                root.seqEditor.addBitVariable(purpose)
            else
                root.seqEditor.addDataVariable(purpose)
        }
        onRenameRequested: function(itemId) { root.seqEditor.renameVariable(kind, itemId) }
        onDeleteRequested: function(itemId) { root.seqEditor.deleteVariable(kind, itemId) }
        onValueRequested: function(itemId) { root.seqEditor.editVariableValue(kind, itemId) }
        onPublishRequested: function(itemId) {
            if (kind === "data")
                root.seqEditor.configureDataPublish(itemId)
            else
                root.seqEditor.toggleVariablePublish(kind, itemId)
        }
        onUnpublishRequested: function(itemId) { root.seqEditor.unpublishData(itemId) }
        onResetRequested: function(itemId) { root.seqEditor.cycleVariableReset(kind, itemId) }
    }

    ModeCardPopup {
        id: modeCardPopup
        items: root.seqEditor ? root.seqEditor.modeCards : []
        currentIndex: root.seqEditor ? root.seqEditor.selectedModeIndex : -1
        onSelected: function(modeIndex) { root.seqEditor.selectModeCondition(modeIndex) }
    }

    SequenceCardPopup {
        id: sequenceCardPopup
        items: root.seqEditor ? root.seqEditor.sequenceCards : []
        currentIndex: root.seqEditor ? root.seqEditor.sequenceIndex : -1
        onSelected: function(index) { root.seqEditor.selectSequence(index) }
        onRenameRequested: function(index) { root.seqEditor.renameSequence(index) }
    }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 10
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 54
            Text { text: "시퀀스 편집"; color: "#65A1FF"; font.pixelSize: 24; font.bold: true }
            EditorButton {
                Layout.preferredWidth: 250
                text: !seqEditor || seqEditor.sequenceIndex < 0
                      ? "프로그램 선택"
                      : "프로그램  ·  " + String(seqEditor.sequenceKeys[seqEditor.sequenceIndex]) + "  ▾"
                accent: "#315D86"
                onClicked: sequenceCardPopup.open()
            }
            EditorButton { Layout.preferredWidth: 100; text: "+ 서브"; accent: "#00B8D4"; onClicked: seqEditor.addSequence() }
            EditorButton { Layout.preferredWidth: 110; text: "서브 삭제"; accent: "#D64C5B"; onClicked: seqEditor.deleteSequence() }
            Item { Layout.fillWidth: true }
            EditorButton { Layout.preferredWidth: 100; text: "취소"; accent: "#8A4E55"; onClicked: seqEditor.cancel() }
            EditorButton { Layout.preferredWidth: 145; text: "저장 후 닫기"; accent: "#468CFF"; onClicked: seqEditor.save() }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            Rectangle {
                Layout.preferredWidth: 4; Layout.fillWidth: true; Layout.fillHeight: true
                color: panel; radius: 10; border.color: borderCol
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    ListView {
                        id: list; Layout.fillWidth: true; Layout.fillHeight: true
                        model: stepModel; clip: true; spacing: 3; boundsBehavior: Flickable.StopAtBounds
                        currentIndex: seqEditor ? seqEditor.selectedRow : -1
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            width: 12
                            contentItem: Rectangle {
                                radius: 6
                                color: parent.pressed ? "#7EB2FF" : "#527CA5"
                            }
                            background: Rectangle { color: "#101821"; radius: 6 }
                        }
                        delegate: Rectangle {
                            property bool commentRow: model.stepType === "COMMENT"
                            property bool selectedRow: index === (seqEditor ? seqEditor.selectedRow : -1)
                            width: list.width
                            height: commentRow ? 42 : 45
                            radius: commentRow ? 2 : 6
                            color: commentRow
                                   ? (selectedRow ? "#393724" : "#22241E")
                                   : (selectedRow ? "#304A63" : "#1D2A37")
                            border.color: commentRow
                                          ? (selectedRow ? "#D6B84A" : "#554F32")
                                          : (selectedRow ? "#7EB2FF" : "#32485D")
                            border.width: selectedRow ? 2 : 1
                            RowLayout {
                                visible: !parent.commentRow
                                anchors.fill: parent; anchors.margins: 4; spacing: 7
                                Rectangle {
                                    Layout.preferredWidth: 30; Layout.fillHeight: true
                                    color: "transparent"
                                    Text {
                                        anchors.centerIn: parent
                                        text: model.displayNumber
                                        color: "#AFC0D0"
                                        font.pixelSize: 14
                                        font.bold: true
                                    }
                                }
                                Rectangle {
                                    property color badgeColor: model.stepColor
                                    Layout.preferredWidth: 58; Layout.preferredHeight: 31
                                    radius: 5
                                    color: Qt.darker(badgeColor, 2.35)
                                    border.color: badgeColor
                                    Text {
                                        anchors.centerIn: parent
                                        text: model.stepType
                                        color: parent.badgeColor
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                }
                                Text {
                                    Layout.preferredWidth: 165
                                    Layout.fillHeight: true
                                    text: model.stepName
                                    color: "#FFFFFF"
                                    font.pixelSize: 14
                                    font.bold: true
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                Rectangle {
                                    Layout.preferredWidth: 1
                                    Layout.preferredHeight: 18
                                    color: "#40566A"
                                    visible: detailText.visible
                                }
                                Text {
                                    id: detailText
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    visible: text.length > 0
                                    text: model.stepDetail
                                    color: "#9FB2C4"
                                    font.pixelSize: 12
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }

                            Rectangle {
                                visible: parent.commentRow
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.margins: 5
                                width: 4
                                radius: 2
                                color: "#D6B84A"
                            }
                            Text {
                                visible: parent.commentRow
                                anchors.left: parent.left
                                anchors.leftMargin: 18
                                anchors.right: parent.right
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: model.stepName
                                color: "#E8D98A"
                                font.pixelSize: 16
                                font.italic: true
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                            MouseArea { anchors.fill: parent; onClicked: seqEditor.selectStep(index) }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        EditorButton { text: "▲ 위로"; Layout.fillWidth: true; accent: "#607D8B"; onClicked: seqEditor.moveSelected(-1) }
                        EditorButton { text: "▼ 아래로"; Layout.fillWidth: true; accent: "#607D8B"; onClicked: seqEditor.moveSelected(1) }
                        EditorButton { text: "스텝 삭제"; Layout.fillWidth: true; accent: "#D64C5B"; onClicked: seqEditor.deleteSelected() }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 6; Layout.fillWidth: true; Layout.fillHeight: true
                color: panel; radius: 10; border.color: borderCol
                ScrollView {
                    id: propertyScroll
                    anchors.fill: parent; anchors.margins: 14; clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                        width: 12
                        contentItem: Rectangle { radius: 6; color: parent.pressed ? "#7EB2FF" : "#527CA5" }
                        background: Rectangle { color: "#101821"; radius: 6 }
                    }
                    ColumnLayout {
                        width: Math.max(0, propertyScroll.availableWidth - 4); spacing: 12
                        Text {
                            text: seqEditor && seqEditor.selectedType === "COMMENT"
                                  ? "코멘트 · 실행 순서에 포함되지 않음"
                                  : (seqEditor && seqEditor.selectedType
                                     ? seqEditor.selectedType + " 스텝"
                                     : "스텝을 선택하세요")
                            color: seqEditor && seqEditor.selectedType === "COMMENT" ? "#D6B84A" : "#65A1FF"
                            font.pixelSize: 23
                            font.bold: true
                        }
                        EditorField {
                            Layout.fillWidth: true; placeholderText: "이름 / 메모"
                            text: seqEditor ? seqEditor.selectedName : ""
                            visible: seqEditor && seqEditor.selectedType !== "" && seqEditor.selectedType !== "COMMENT"
                            enabled: visible
                            onEditingFinished: seqEditor.setName(text)
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 64
                            visible: seqEditor && seqEditor.selectedType === "COMMENT"
                            radius: 8
                            color: commentEditArea.pressed ? "#343425" : "#20231E"
                            border.color: commentEditArea.pressed ? "#F0D363" : "#71683D"
                            border.width: 2
                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 16
                                text: seqEditor && seqEditor.selectedName !== ""
                                      ? seqEditor.selectedName
                                      : "메모를 입력하려면 터치하세요"
                                color: "#E8D98A"
                                font.pixelSize: 18
                                font.italic: true
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                            }
                            MouseArea {
                                id: commentEditArea
                                anchors.fill: parent
                                onClicked: seqEditor.editComment()
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "WPOS"
                            Layout.preferredHeight: visible ? wposContent.implicitHeight + 24 : 0
                            color: "#17222D"
                            radius: 8
                            border.color: "#3B536A"
                            ColumnLayout {
                                id: wposContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 9

                                Text {
                                    text: "실제 위치 도달 대기"
                                    color: "#66D4E1"
                                    font.pixelSize: 18
                                    font.bold: true
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "기준 포인트"; color: "white"; font.pixelSize: 16 }
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: seqEditor ? seqEditor.pointKeys : []
                                        currentIndex: seqEditor ? seqEditor.selectedPointIndex : -1
                                        onActivated: seqEditor.setPointIndex(currentIndex)
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "허용오차"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: "±" + (seqEditor
                                              ? seqEditor.selectedPositionTolerance.toFixed(3)
                                              : "0.100")
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editWaitPositionTolerance()
                                    }
                                    Text { text: "최대 대기"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: (seqEditor
                                              ? seqEditor.selectedPositionTimeout.toFixed(3)
                                              : "5.000") + " s"
                                        accent: "#C36B4A"
                                        onClicked: seqEditor.editWaitPositionTimeout()
                                    }
                                }
                                Text {
                                    text: "비교할 축 선택 · 괄호 안은 포인트 목표위치"
                                    color: "#91A5B8"
                                    font.pixelSize: 13
                                }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4
                                    columnSpacing: 8
                                    rowSpacing: 2
                                    Repeater {
                                        model: seqEditor ? seqEditor.waitPositionAxisRows : []
                                        delegate: EditorCheck {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            text: String(modelData.name) + " (" + String(modelData.target) + ")"
                                            checked: Boolean(modelData.active)
                                            onClicked: seqEditor.setAxisActive(
                                                Number(modelData.index), checked)
                                        }
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: "선택한 모든 축이 허용오차 안에 들어오면 다음 스텝으로 진행합니다. 타임아웃 시 자동운전을 오류 정지합니다."
                                    color: "#E3A06F"
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "POS"
                            Layout.preferredHeight: visible ? posContent.implicitHeight + 24 : 0
                            color: "#17222D"
                            radius: 8
                            border.color: "#3B536A"
                            ColumnLayout {
                                id: posContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 9

                                Text {
                                    text: "목표 위치 포인트"
                                    color: "#8FB9E8"
                                    font.pixelSize: 18
                                    font.bold: true
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 7
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: seqEditor ? seqEditor.pointKeys : []
                                        currentIndex: seqEditor ? seqEditor.selectedPointIndex : -1
                                        onActivated: seqEditor.setPointIndex(currentIndex)
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 62
                                        text: "+ 추가"
                                        accent: "#468CFF"
                                        onClicked: seqEditor.addPositionPoint()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 62
                                        text: "이름"
                                        accent: "#7C8FA3"
                                        enabled: seqEditor && seqEditor.hasSelectedPoint
                                        onClicked: seqEditor.renameSelectedPoint()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 62
                                        text: "삭제"
                                        accent: "#D64C5B"
                                        enabled: seqEditor && seqEditor.hasSelectedPoint
                                        onClicked: seqEditor.deleteSelectedPoint()
                                    }
                                }

                                Text {
                                    visible: seqEditor && !seqEditor.hasSelectedPoint
                                    text: "등록된 위치 포인트가 없습니다. + 추가 버튼으로 먼저 등록하세요."
                                    color: "#F0B26B"
                                    font.pixelSize: 14
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 1
                                    color: "#344B60"
                                }
                                Text {
                                    text: "다음 스텝 이행"
                                    color: "#8FB9E8"
                                    font.pixelSize: 17
                                    font.bold: true
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: "완료 후 이행"
                                        accent: seqEditor && seqEditor.selectedWaitCompletion
                                                ? "#468CFF" : "#546677"
                                        onClicked: seqEditor.setWaitCompletion(true)
                                    }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: "동시 이행"
                                        accent: seqEditor && !seqEditor.selectedWaitCompletion
                                                ? "#468CFF" : "#546677"
                                        onClicked: seqEditor.setWaitCompletion(false)
                                    }
                                    EditorCheck {
                                        Layout.preferredWidth: 190
                                        text: "파렛타이징 베이스"
                                        checked: seqEditor && seqEditor.selectedPackBase
                                        onClicked: seqEditor.setPackBase(checked)
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 1
                                    color: "#344B60"
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text {
                                        text: "축별 목표위치 및 속도"
                                        color: "#8FB9E8"
                                        font.pixelSize: 17
                                        font.bold: true
                                    }
                                    Item { Layout.fillWidth: true }
                                    Text {
                                        text: "값을 터치하면 직접 입력"
                                        color: "#8096AA"
                                        font.pixelSize: 13
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 7
                                    Text {
                                        Layout.preferredWidth: 82
                                        text: "사용"
                                        color: "#AFC0D0"
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                    Text {
                                        Layout.preferredWidth: 42
                                        text: "축"
                                        color: "#AFC0D0"
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: "목표위치 (mm)"
                                        color: "#AFC0D0"
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                    Text {
                                        Layout.preferredWidth: 118
                                        text: "속도 (%)"
                                        color: "#AFC0D0"
                                        horizontalAlignment: Text.AlignHCenter
                                        font.pixelSize: 13
                                        font.bold: true
                                    }
                                }

                                Repeater {
                                    model: seqEditor ? seqEditor.positionAxisRows : []
                                    delegate: Rectangle {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 43
                                        color: modelData.active ? "#1C2D3C" : "#18232D"
                                        radius: 6
                                        border.color: modelData.active ? "#3F668A" : "#304253"
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 4
                                            spacing: 7
                                            EditorButton {
                                                Layout.preferredWidth: 78
                                                Layout.fillHeight: true
                                                text: modelData.active ? "사용" : "미사용"
                                                accent: modelData.active ? "#468CFF" : "#546677"
                                                onClicked: seqEditor.setAxisActive(
                                                    modelData.index, !modelData.active)
                                            }
                                            Text {
                                                Layout.preferredWidth: 42
                                                text: modelData.name
                                                color: "#FFFFFF"
                                                font.pixelSize: 16
                                                font.bold: true
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                            EditorButton {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                text: modelData.position + " mm"
                                                accent: "#27A58D"
                                                enabled: seqEditor && seqEditor.hasSelectedPoint
                                                onClicked: seqEditor.editPointCoordinate(modelData.index)
                                            }
                                            EditorButton {
                                                Layout.preferredWidth: 110
                                                Layout.fillHeight: true
                                                text: modelData.speed + " %"
                                                accent: "#C08B38"
                                                enabled: seqEditor && seqEditor.hasSelectedPoint
                                                onClicked: seqEditor.editPointSpeed(modelData.index)
                                            }
                                        }
                                    }
                                }
                                Text {
                                    text: "※ 목표위치와 속도는 같은 포인트를 사용하는 모든 POS 스텝에 공통 적용됩니다."
                                    color: "#8096AA"
                                    font.pixelSize: 12
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && (seqEditor.selectedType === "OUT" || seqEditor.selectedType === "IN")
                            Layout.preferredHeight: visible ? ioContent.implicitHeight + 24 : 0
                            color: "#17222D"; radius: 8; border.color: "#3B536A"
                            ColumnLayout {
                                id: ioContent
                                anchors.fill: parent; anchors.margins: 12; spacing: 10
                                Text {
                                    text: seqEditor && seqEditor.selectedType === "OUT" ? "출력 조건" : "입력 대기 조건"
                                    color: "#8FB9E8"; font.pixelSize: 18; font.bold: true
                                }
                                RowLayout {
                                    Text { text: "종류"; color: "white"; font.pixelSize: 17 }
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: seqEditor && seqEditor.selectedType === "OUT"
                                               ? ["출력 (Y)", "내부비트"]
                                               : ["입력 (X)", "내부비트"]
                                        currentIndex: seqEditor ? seqEditor.selectedAddressClass : 0
                                        onActivated: seqEditor.setAddressClass(currentIndex)
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 90
                                        text: seqEditor && seqEditor.selectedOn ? "ON" : "OFF"
                                        accent: seqEditor && seqEditor.selectedOn ? "#16A085" : "#C34A55"
                                        onClicked: seqEditor.setOn(!seqEditor.selectedOn)
                                    }
                                }
                                RowLayout {
                                    Text { text: "주소"; color: "white"; font.pixelSize: 17 }
                                    EditorCombo {
                                        visible: seqEditor && seqEditor.selectedAddressClass === 0
                                        Layout.fillWidth: true
                                        model: seqEditor ? seqEditor.addressKeys : []
                                        currentIndex: seqEditor ? seqEditor.selectedAddressIndex : 0
                                        onActivated: seqEditor.setAddressIndex(currentIndex)
                                    }
                                    EditorButton {
                                        visible: seqEditor && seqEditor.selectedAddressClass === 1
                                        Layout.fillWidth: true
                                        text: seqEditor ? seqEditor.selectedIoBitName : "내부비트 선택"
                                        accent: "#35A98B"
                                        onClicked: {
                                            variableCardPopup.purpose = "io_bit"
                                            variableCardPopup.open()
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "OUT"
                            Layout.preferredHeight: visible ? outDelayContent.implicitHeight + 24 : 0
                            color: "#17222D"; radius: 8; border.color: "#3B536A"
                            ColumnLayout {
                                id: outDelayContent
                                anchors.fill: parent; anchors.margins: 12; spacing: 9
                                RowLayout {
                                    Text { text: "지연 출력 설정"; color: "#8FB9E8"; font.pixelSize: 18; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    EditorCheck {
                                        text: "사용"
                                        checked: seqEditor && seqEditor.selectedDelayEnabled
                                        onClicked: seqEditor.setDelayEnabled(checked)
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedDelayEnabled
                                    Text { text: "타이머"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: seqEditor && seqEditor.selectedLibraryTimerName !== ""
                                              ? seqEditor.selectedLibraryTimerName
                                              : "직접 설정"
                                        accent: "#607D8B"
                                        onClicked: {
                                            timerCardPopup.purpose = "step"
                                            timerCardPopup.open()
                                        }
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 105
                                        text: "+ 추가"
                                        accent: "#00B8D4"
                                        onClicked: seqEditor.addLibraryTimer()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 85
                                        text: "삭제"
                                        accent: "#D64C5B"
                                        enabled: seqEditor && seqEditor.selectedLibraryTimerIndex > 0
                                        onClicked: seqEditor.deleteLibraryTimer()
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedDelayEnabled
                                    Text { text: "지연 시간"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.preferredWidth: 210
                                        text: (seqEditor ? seqEditor.selectedDelaySeconds.toFixed(2) : "0.00") + " s"
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editLibraryTimerSeconds()
                                    }
                                    Text {
                                        text: "터치하여 직접 입력"
                                        color: "#91A5B8"
                                        font.pixelSize: 14
                                    }
                                    Item { Layout.fillWidth: true }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "IN"
                            Layout.preferredHeight: visible ? inputWaitContent.implicitHeight + 24 : 0
                            color: "#17222D"; radius: 8; border.color: "#3B536A"
                            ColumnLayout {
                                id: inputWaitContent
                                anchors.fill: parent; anchors.margins: 12; spacing: 9
                                RowLayout {
                                    Text { text: "입력 대기 조건"; color: "#8FB9E8"; font.pixelSize: 18; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    EditorCheck {
                                        text: "타임업 조건 사용"
                                        checked: seqEditor && seqEditor.selectedTimeupEnabled
                                        onClicked: seqEditor.setTimeupEnabled(checked)
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedTimeupEnabled
                                    Text { text: "타이머"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: seqEditor && seqEditor.selectedTimeupTimerName !== ""
                                              ? seqEditor.selectedTimeupTimerName
                                              : "직접 설정"
                                        accent: "#607D8B"
                                        onClicked: {
                                            timerCardPopup.purpose = "timeup"
                                            timerCardPopup.open()
                                        }
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 105
                                        text: "+ 추가"
                                        accent: "#00B8D4"
                                        onClicked: seqEditor.addTimeupTimer()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 85
                                        text: "삭제"
                                        accent: "#D64C5B"
                                        enabled: seqEditor && seqEditor.selectedTimeupTimerIndex > 0
                                        onClicked: seqEditor.deleteTimeupTimer()
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedTimeupEnabled
                                    Text { text: "신호 유지시간"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.preferredWidth: 210
                                        text: (seqEditor ? seqEditor.selectedTimeupSeconds.toFixed(2) : "0.00") + " s"
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editTimeupSeconds()
                                    }
                                    Text { text: "터치하여 직접 입력"; color: "#91A5B8"; font.pixelSize: 14 }
                                    Item { Layout.fillWidth: true }
                                }

                                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: "#3B536A" }

                                RowLayout {
                                    Text { text: "최대 대기시간 / 알람"; color: "#8FB9E8"; font.pixelSize: 18; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    EditorCheck {
                                        text: "타임아웃 사용"
                                        checked: seqEditor && seqEditor.selectedTimeoutEnabled
                                        onClicked: seqEditor.setTimeoutEnabled(checked)
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedTimeoutEnabled
                                    Text { text: "타이머"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: seqEditor && seqEditor.selectedTimeoutTimerName !== ""
                                              ? seqEditor.selectedTimeoutTimerName
                                              : "직접 설정"
                                        accent: "#607D8B"
                                        onClicked: {
                                            timerCardPopup.purpose = "timeout"
                                            timerCardPopup.open()
                                        }
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 105
                                        text: "+ 추가"
                                        accent: "#00B8D4"
                                        onClicked: seqEditor.addTimeoutTimer()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 85
                                        text: "삭제"
                                        accent: "#D64C5B"
                                        enabled: seqEditor && seqEditor.selectedTimeoutTimerIndex > 0
                                        onClicked: seqEditor.deleteTimeoutTimer()
                                    }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedTimeoutEnabled
                                    Text { text: "최대 대기시간"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.preferredWidth: 210
                                        text: (seqEditor ? seqEditor.selectedTimeoutSeconds.toFixed(2) : "0.00") + " s"
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editTimeoutSeconds()
                                    }
                                    Text { text: "터치하여 직접 입력"; color: "#91A5B8"; font.pixelSize: 14 }
                                    Item { Layout.fillWidth: true }
                                }
                                RowLayout {
                                    enabled: seqEditor && seqEditor.selectedTimeoutEnabled
                                    Text { text: "시간 초과 시"; color: "white"; font.pixelSize: 16 }
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: ["알람 후 진행여부 선택", "알람 표시 후 정지", "알람 표시 후 진행"]
                                        currentIndex: seqEditor ? seqEditor.selectedTimeoutAction : 0
                                        onActivated: seqEditor.setTimeoutAction(currentIndex)
                                    }
                                }
                                RowLayout {
                                    visible: seqEditor && seqEditor.selectedTimeoutEnabled
                                    Text { text: "사용자 알람"; color: "white"; font.pixelSize: 16 }
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: seqEditor ? seqEditor.timeoutAlarmChoices : []
                                        currentIndex: seqEditor ? seqEditor.selectedTimeoutAlarmIndex : 0
                                        onActivated: seqEditor.setTimeoutAlarmIndex(currentIndex)
                                    }
                                    EditorSpin {
                                        from: 1; to: 999
                                        value: seqEditor ? seqEditor.selectedTimeoutAlarmNo : 1
                                        onValueModified: function(value) { seqEditor.setTimeoutAlarmNo(value) }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "TMR"
                            Layout.preferredHeight: visible ? timerContent.implicitHeight + 24 : 0
                            color: "#17222D"; radius: 8; border.color: "#3B536A"
                            ColumnLayout {
                                id: timerContent
                                anchors.fill: parent; anchors.margins: 12; spacing: 10
                                Text { text: "타이머 설정"; color: "#8FB9E8"; font.pixelSize: 18; font.bold: true }
                                RowLayout {
                                    Text { text: "타이머"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: seqEditor && seqEditor.selectedLibraryTimerName !== ""
                                              ? seqEditor.selectedLibraryTimerName
                                              : "직접 설정"
                                        accent: "#607D8B"
                                        onClicked: {
                                            timerCardPopup.purpose = "step"
                                            timerCardPopup.open()
                                        }
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 105
                                        text: "+ 추가"
                                        accent: "#00B8D4"
                                        onClicked: seqEditor.addLibraryTimer()
                                    }
                                    EditorButton {
                                        Layout.preferredWidth: 85
                                        text: "삭제"
                                        accent: "#D64C5B"
                                        enabled: seqEditor && seqEditor.selectedLibraryTimerIndex > 0
                                        onClicked: seqEditor.deleteLibraryTimer()
                                    }
                                }
                                RowLayout {
                                    Text { text: "대기 시간"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.preferredWidth: 210
                                        text: (seqEditor ? seqEditor.selectedSeconds : 0).toFixed(2) + " s"
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editLibraryTimerSeconds()
                                    }
                                    Text { text: "터치하여 직접 입력"; color: "#91A5B8"; font.pixelSize: 14 }
                                    Item { Layout.fillWidth: true }
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; visible: seqEditor && seqEditor.selectedType === "JMP"
                            RowLayout {
                                Text { text: "이동 대상"; color: "white" }
                                EditorCombo { Layout.fillWidth: true; model: seqEditor ? seqEditor.stepTargets : []
                                           currentIndex: seqEditor ? seqEditor.selectedTargetIndex : 0
                                           onActivated: seqEditor.setTargetIndex(currentIndex) }
                                EditorCheck { text: "조건부"; checked: seqEditor && seqEditor.selectedConditional
                                           onClicked: seqEditor.setConditional(checked) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedConditional
                                EditorCombo { Layout.fillWidth: true; model: ["입력 (X)", "내부비트", "모드", "운전상태", "데이터 비교", "포인트 위치"]
                                           currentIndex: seqEditor ? seqEditor.selectedCondType : 0
                                           onActivated: seqEditor.setCondType(currentIndex) }
                                EditorButton {
                                    visible: seqEditor && seqEditor.selectedCondType === 2
                                    Layout.preferredWidth: 245
                                    text: seqEditor ? seqEditor.selectedModeName : "모드 선택"
                                    accent: "#766BC7"
                                    onClicked: modeCardPopup.open()
                                }
                                EditorCombo {
                                    visible: seqEditor && seqEditor.selectedCondType === 3
                                    Layout.preferredWidth: 210
                                    model: ["정지", "자동", "확인운전", "알람발생"]
                                    currentIndex: seqEditor ? seqEditor.selectedRunStateIndex : 0
                                    onActivated: seqEditor.setRunStateIndex(currentIndex)
                                }
                                EditorButton { visible: seqEditor && seqEditor.selectedCondType !== 3
                                                       && seqEditor.selectedCondType !== 4
                                         text: seqEditor && seqEditor.selectedCondType === 5
                                               ? (seqEditor.selectedCondOn ? "일치할 때" : "불일치할 때")
                                               : (seqEditor && seqEditor.selectedCondOn ? "ON 일 때" : "OFF 일 때")
                                         accent: seqEditor && seqEditor.selectedCondOn ? "#16A085" : "#C34A55"
                                         onClicked: seqEditor.setCondOn(!seqEditor.selectedCondOn) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedConditional && seqEditor.selectedCondType < 2
                                Text { text: "조건 주소"; color: "white"; font.pixelSize: 16 }
                                EditorCombo {
                                    visible: seqEditor && seqEditor.selectedCondType === 0
                                    Layout.fillWidth: true
                                    model: seqEditor ? seqEditor.condAddressKeys : []
                                    currentIndex: seqEditor ? seqEditor.selectedCondAddressIndex : 0
                                    onActivated: seqEditor.setCondAddressIndex(currentIndex)
                                }
                                EditorButton {
                                    visible: seqEditor && seqEditor.selectedCondType === 1
                                    Layout.fillWidth: true
                                    text: seqEditor ? seqEditor.selectedCondBitName : "내부비트 선택"
                                    accent: "#35A98B"
                                    onClicked: {
                                        variableCardPopup.purpose = "cond_bit"
                                        variableCardPopup.open()
                                    }
                                }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedConditional && seqEditor.selectedCondType === 4
                                Text { text: "데이터"; color: "white" }
                                EditorButton {
                                    Layout.fillWidth: true
                                    text: seqEditor ? seqEditor.selectedCmpDataName : "데이터 선택"
                                    accent: "#468CFF"
                                    onClicked: {
                                        variableCardPopup.purpose = "cmp_data"
                                        variableCardPopup.open()
                                    }
                                }
                                EditorCombo { Layout.preferredWidth: 90; model: ["=", "≠", ">", "≥", "<", "≤"]
                                           currentIndex: seqEditor ? seqEditor.selectedCmpOp : 0
                                           onActivated: seqEditor.setCmpOp(currentIndex) }
                                EditorSpin { from: -2147483647; to: 2147483647
                                          value: seqEditor ? seqEditor.selectedCmpConst : 0
                                          onValueModified: function(value) { seqEditor.setCmpConst(value) } }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                visible: seqEditor && seqEditor.selectedConditional
                                         && seqEditor.selectedCondType === 5
                                spacing: 7
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "기준 포인트"; color: "white"; font.pixelSize: 16 }
                                    EditorCombo {
                                        Layout.fillWidth: true
                                        model: seqEditor ? seqEditor.pointKeys : []
                                        currentIndex: seqEditor ? seqEditor.selectedCondPointIndex : -1
                                        onActivated: seqEditor.setCondPointIndex(currentIndex)
                                    }
                                    Text { text: "허용오차"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.preferredWidth: 145
                                        text: "±" + (seqEditor
                                              ? seqEditor.selectedPositionCondTolerance.toFixed(3)
                                              : "0.100")
                                        accent: "#D6A928"
                                        onClicked: seqEditor.editPositionCondTolerance()
                                    }
                                }
                                Text {
                                    text: "비교할 축 선택 · 괄호 안은 포인트 목표위치"
                                    color: "#91A5B8"
                                    font.pixelSize: 13
                                }
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4
                                    columnSpacing: 8
                                    rowSpacing: 2
                                    Repeater {
                                        model: seqEditor ? seqEditor.positionCondAxisRows : []
                                        delegate: EditorCheck {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            text: String(modelData.name) + " (" + String(modelData.target) + ")"
                                            checked: Boolean(modelData.active)
                                            onClicked: seqEditor.setPositionCondAxisActive(
                                                Number(modelData.index), checked)
                                        }
                                    }
                                }
                            }
                        }

                        RowLayout {
                            visible: seqEditor && seqEditor.selectedType === "CALL"
                            Text { text: "호출"; color: "white" }
                            EditorCombo { Layout.fillWidth: true; model: seqEditor ? seqEditor.targetSequenceKeys : []
                                       currentIndex: seqEditor ? seqEditor.targetSequenceIndex : -1
                                       onActivated: seqEditor.setTargetSequenceIndex(currentIndex) }
                            EditorCheck { text: "동시 실행"; checked: seqEditor && seqEditor.selectedParallel
                                       onClicked: seqEditor.setParallel(checked) }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            visible: seqEditor && seqEditor.selectedType === "DAT"
                            Layout.preferredHeight: visible ? datContent.implicitHeight + 24 : 0
                            color: "#17222D"
                            radius: 8
                            border.color: "#3B536A"
                            ColumnLayout {
                                id: datContent
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 10

                                Text {
                                    text: "데이터 연산"
                                    color: "#72E6B8"
                                    font.pixelSize: 18
                                    font.bold: true
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "결과 데이터"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: seqEditor ? seqEditor.selectedDatDataName : "결과 데이터 선택"
                                        accent: "#468CFF"
                                        onClicked: {
                                            variableCardPopup.purpose = "dat_data"
                                            variableCardPopup.open()
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "연산 방식"; color: "white"; font.pixelSize: 16 }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: "상수 연산"
                                        accent: seqEditor && seqEditor.selectedDatMode === 0
                                                ? "#00A982" : "#546677"
                                        onClicked: seqEditor.setDatMode(0)
                                    }
                                    EditorButton {
                                        Layout.fillWidth: true
                                        text: "데이터 사칙연산"
                                        accent: seqEditor && seqEditor.selectedDatMode === 1
                                                ? "#00A982" : "#546677"
                                        onClicked: seqEditor.setDatMode(1)
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    visible: seqEditor && seqEditor.selectedDatMode === 0
                                    EditorCombo {
                                        Layout.preferredWidth: 180
                                        model: ["대입 (=)", "가산 (+=)", "감산 (-=)"]
                                        currentIndex: seqEditor ? seqEditor.selectedDatOp : 0
                                        onActivated: seqEditor.setDatOp(currentIndex)
                                    }
                                    EditorSpin {
                                        Layout.fillWidth: true
                                        from: -2147483647
                                        to: 2147483647
                                        value: seqEditor ? seqEditor.selectedDatConst : 0
                                        onValueModified: function(value) { seqEditor.setDatConst(value) }
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: seqEditor && seqEditor.selectedDatMode === 1
                                    spacing: 9
                                    RowLayout {
                                        Layout.fillWidth: true
                                        EditorButton {
                                            Layout.fillWidth: true
                                            text: seqEditor ? seqEditor.selectedDatLeftDataName : "데이터 A 선택"
                                            accent: "#5C83C7"
                                            onClicked: {
                                                variableCardPopup.purpose = "dat_left_data"
                                                variableCardPopup.open()
                                            }
                                        }
                                        EditorCombo {
                                            Layout.preferredWidth: 135
                                            model: ["더하기 (+)", "빼기 (−)", "곱하기 (×)", "나누기 (÷)"]
                                            currentIndex: seqEditor ? seqEditor.selectedDatMathOp : 0
                                            onActivated: seqEditor.setDatMathOp(currentIndex)
                                        }
                                        EditorButton {
                                            Layout.fillWidth: true
                                            text: seqEditor ? seqEditor.selectedDatRightDataName : "데이터 B 선택"
                                            accent: "#5C83C7"
                                            onClicked: {
                                                variableCardPopup.purpose = "dat_right_data"
                                                variableCardPopup.open()
                                            }
                                        }
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 52
                                        radius: 7
                                        color: "#1E303D"
                                        border.color: "#3D6076"
                                        Text {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            text: (seqEditor ? seqEditor.selectedDatDataName : "결과")
                                                  + " = "
                                                  + (seqEditor ? seqEditor.selectedDatLeftDataName : "A")
                                                  + " " + root.datMathSymbols[seqEditor ? seqEditor.selectedDatMathOp : 0] + " "
                                                  + (seqEditor ? seqEditor.selectedDatRightDataName : "B")
                                            color: "#CFFFE9"
                                            font.pixelSize: 16
                                            font.bold: true
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                            elide: Text.ElideRight
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: "나눗셈 결과는 소수점 이하를 버린 정수이며, 0으로 나누면 실행 오류로 정지합니다."
                                        color: "#91A5B8"
                                        font.pixelSize: 13
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                        Item { Layout.preferredHeight: 20 }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: ["POS", "WPOS", "OUT", "IN", "TMR", "JMP", "CALL", "DAT", "END", "COMMENT"]
                EditorButton {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 46
                    text: modelData === "POS" && seqEditor && seqEditor.isMonitorSequence
                          ? "POS 금지"
                          : "+ " + (modelData === "COMMENT" ? "CMT" : modelData)
                    accent: root.stepColor(modelData)
                    enabled: !(modelData === "POS" && seqEditor && seqEditor.isMonitorSequence)
                    onClicked: seqEditor.addStep(modelData)
                }
            }
        }
    }
}
