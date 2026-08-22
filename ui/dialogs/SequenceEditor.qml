import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    color: "#0F161E"
    property color panel: "#17222E"
    property color borderCol: "#35506A"
    property var axisNames: ["X", "Y", "Z", "Y2", "Z2", "θ", "R1", "R2"]

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 10
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 54
            Text { text: "시퀀스 편집"; color: "#65A1FF"; font.pixelSize: 24; font.bold: true }
            ComboBox {
                Layout.preferredWidth: 250; model: seqEditor ? seqEditor.sequenceKeys : []
                currentIndex: seqEditor ? seqEditor.sequenceIndex : 0
                onActivated: if (seqEditor) seqEditor.selectSequence(currentIndex)
            }
            Button { text: "+ 서브"; onClicked: seqEditor.addSequence() }
            Button { text: "서브 삭제"; onClicked: seqEditor.deleteSequence() }
            Item { Layout.fillWidth: true }
            Button { text: "취소"; onClicked: seqEditor.cancel() }
            Button { text: "저장 후 닫기"; highlighted: true; onClicked: seqEditor.save() }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 12
            Rectangle {
                Layout.preferredWidth: 430; Layout.fillHeight: true; color: panel; radius: 10; border.color: borderCol
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    ListView {
                        id: list; Layout.fillWidth: true; Layout.fillHeight: true
                        model: stepModel; clip: true; spacing: 5; boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Rectangle {
                            width: list.width; height: 54; radius: 7
                            color: index === (seqEditor ? seqEditor.selectedRow : -1) ? "#354F6B" : "#202F3E"
                            border.color: model.stepColor; border.width: index === seqEditor.selectedRow ? 2 : 1
                            Row {
                                anchors.fill: parent; anchors.margins: 8; spacing: 10
                                Rectangle { width: 8; height: parent.height; radius: 4; color: model.stepColor }
                                Text { width: parent.width - 26; anchors.verticalCenter: parent.verticalCenter
                                       text: (index + 1) + ". " + model.summary; color: "white"
                                       font.pixelSize: 17; elide: Text.ElideRight }
                            }
                            MouseArea { anchors.fill: parent; onClicked: seqEditor.selectStep(index) }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button { text: "▲"; Layout.fillWidth: true; onClicked: seqEditor.moveSelected(-1) }
                        Button { text: "▼"; Layout.fillWidth: true; onClicked: seqEditor.moveSelected(1) }
                        Button { text: "삭제"; Layout.fillWidth: true; onClicked: seqEditor.deleteSelected() }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true; color: panel; radius: 10; border.color: borderCol
                ScrollView {
                    anchors.fill: parent; anchors.margins: 14; clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ColumnLayout {
                        width: Math.max(0, parent.width - 12); spacing: 12
                        Text { text: seqEditor && seqEditor.selectedType ? seqEditor.selectedType + " 스텝" : "스텝을 선택하세요"
                               color: "#65A1FF"; font.pixelSize: 23; font.bold: true }
                        TextField {
                            Layout.fillWidth: true; placeholderText: "이름 / 메모"
                            text: seqEditor ? seqEditor.selectedName : ""
                            enabled: seqEditor && seqEditor.selectedType !== ""
                            onEditingFinished: seqEditor.setName(text)
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; visible: seqEditor && seqEditor.selectedType === "POS"
                            RowLayout {
                                Text { text: "위치 포인트"; color: "white"; font.pixelSize: 18 }
                                ComboBox { Layout.fillWidth: true; model: seqEditor ? seqEditor.pointKeys : []
                                           currentIndex: seqEditor ? seqEditor.selectedPointIndex : -1
                                           onActivated: seqEditor.setPointIndex(currentIndex) }
                                CheckBox { text: "완료 후 이행"; checked: seqEditor && seqEditor.selectedWaitCompletion
                                           onToggled: seqEditor.setWaitCompletion(checked) }
                                CheckBox { text: "파렛타이징 베이스"; checked: seqEditor && seqEditor.selectedPackBase
                                           onToggled: seqEditor.setPackBase(checked) }
                            }
                            Flow {
                                Layout.fillWidth: true; spacing: 6
                                Repeater {
                                    model: 8
                                    Button {
                                        required property int index
                                        property bool axisOn: seqEditor ? (seqEditor.selectedRow, seqEditor.axisActive(index)) : false
                                        text: axisNames[index] + " " + (axisOn ? "ON" : "OFF")
                                        highlighted: axisOn; width: 90
                                        onClicked: seqEditor.setAxisActive(index, !axisOn)
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            visible: seqEditor && (seqEditor.selectedType === "OUT" || seqEditor.selectedType === "IN")
                            RowLayout {
                                Text { text: "구분"; color: "white"; font.pixelSize: 18 }
                                ComboBox { model: ["시스템 I/O", "밸브 I/O", "내부비트"]
                                           currentIndex: seqEditor ? seqEditor.selectedIoType : 0
                                           onActivated: seqEditor.setIoType(currentIndex) }
                                Text { text: "채널"; color: "white"; font.pixelSize: 18 }
                                Button { text: "−"; onClicked: seqEditor.setChannel(seqEditor.selectedChannel - 1) }
                                Text { text: seqEditor ? seqEditor.selectedChannel : 0; color: "#FFD166"; font.pixelSize: 26; font.bold: true }
                                Button { text: "+"; onClicked: seqEditor.setChannel(seqEditor.selectedChannel + 1) }
                                Item { Layout.fillWidth: true }
                                Button { text: seqEditor && seqEditor.selectedOn ? "ON" : "OFF"
                                         highlighted: seqEditor && seqEditor.selectedOn
                                         onClicked: seqEditor.setOn(!seqEditor.selectedOn) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedType === "OUT"
                                CheckBox { text: "지연 출력"; checked: seqEditor && seqEditor.selectedDelayEnabled
                                           onToggled: seqEditor.setDelayEnabled(checked) }
                                Text { text: "지연 " + (seqEditor ? seqEditor.selectedDelaySeconds.toFixed(2) : "0.00") + " s"; color: "white" }
                                Button { text: "−0.1"; onClicked: seqEditor.setDelaySeconds(seqEditor.selectedDelaySeconds - 0.1) }
                                Button { text: "+0.1"; onClicked: seqEditor.setDelaySeconds(seqEditor.selectedDelaySeconds + 0.1) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedType === "IN"
                                CheckBox { text: "타임아웃"; checked: seqEditor && seqEditor.selectedTimeoutEnabled
                                           onToggled: seqEditor.setTimeoutEnabled(checked) }
                                Text { text: (seqEditor ? seqEditor.selectedTimeoutSeconds.toFixed(1) : "0.0") + " s"; color: "white" }
                                Button { text: "−1"; onClicked: seqEditor.setTimeoutSeconds(seqEditor.selectedTimeoutSeconds - 1) }
                                Button { text: "+1"; onClicked: seqEditor.setTimeoutSeconds(seqEditor.selectedTimeoutSeconds + 1) }
                                ComboBox { model: ["계속 대기", "알람 정지", "알람 후 진행"]
                                           currentIndex: seqEditor ? seqEditor.selectedTimeoutAction : 0
                                           onActivated: seqEditor.setTimeoutAction(currentIndex) }
                            }
                        }

                        RowLayout {
                            visible: seqEditor && seqEditor.selectedType === "TMR"
                            Text { text: "시간"; color: "white"; font.pixelSize: 19 }
                            Button { text: "−0.1"; onClicked: seqEditor.setSeconds(seqEditor.selectedSeconds - 0.1) }
                            Text { text: (seqEditor ? seqEditor.selectedSeconds : 0).toFixed(3) + " s"; color: "#FFD166"; font.pixelSize: 28 }
                            Button { text: "+0.1"; onClicked: seqEditor.setSeconds(seqEditor.selectedSeconds + 0.1) }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; visible: seqEditor && seqEditor.selectedType === "JMP"
                            RowLayout {
                                Text { text: "이동 대상"; color: "white" }
                                ComboBox { Layout.fillWidth: true; model: seqEditor ? seqEditor.stepTargets : []
                                           currentIndex: seqEditor ? seqEditor.selectedTargetIndex : 0
                                           onActivated: seqEditor.setTargetIndex(currentIndex) }
                                CheckBox { text: "조건부"; checked: seqEditor && seqEditor.selectedConditional
                                           onToggled: seqEditor.setConditional(checked) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedConditional
                                ComboBox { model: ["시스템 입력", "밸브 입력", "내부비트", "모드", "운전상태", "DT 비교"]
                                           currentIndex: seqEditor ? seqEditor.selectedCondType : 0
                                           onActivated: seqEditor.setCondType(currentIndex) }
                                SpinBox { visible: seqEditor && seqEditor.selectedCondType !== 5
                                          from: 0; to: 131; value: seqEditor ? seqEditor.selectedCondValue : 0
                                          onValueModified: seqEditor.setCondValue(value) }
                                Button { visible: seqEditor && seqEditor.selectedCondType !== 5
                                         text: seqEditor && seqEditor.selectedCondOn ? "ON 일 때" : "OFF 일 때"
                                         onClicked: seqEditor.setCondOn(!seqEditor.selectedCondOn) }
                            }
                            RowLayout {
                                visible: seqEditor && seqEditor.selectedConditional && seqEditor.selectedCondType === 5
                                Text { text: "DT"; color: "white" }
                                SpinBox { from: 60000; to: 60099; value: seqEditor ? seqEditor.selectedCmpAddress : 60000
                                          onValueModified: seqEditor.setCmpAddress(value) }
                                ComboBox { model: ["=", "≠", ">", "≥", "<", "≤"]
                                           currentIndex: seqEditor ? seqEditor.selectedCmpOp : 0
                                           onActivated: seqEditor.setCmpOp(currentIndex) }
                                SpinBox { from: -32768; to: 32767; editable: true
                                          value: seqEditor ? seqEditor.selectedCmpConst : 0
                                          onValueModified: seqEditor.setCmpConst(value) }
                            }
                        }

                        RowLayout {
                            visible: seqEditor && seqEditor.selectedType === "CALL"
                            Text { text: "호출"; color: "white" }
                            ComboBox { Layout.fillWidth: true; model: seqEditor ? seqEditor.targetSequenceKeys : []
                                       currentIndex: seqEditor ? seqEditor.targetSequenceIndex : -1
                                       onActivated: seqEditor.setTargetSequenceIndex(currentIndex) }
                            CheckBox { text: "동시 실행"; checked: seqEditor && seqEditor.selectedParallel
                                       onToggled: seqEditor.setParallel(checked) }
                        }

                        RowLayout {
                            visible: seqEditor && seqEditor.selectedType === "DAT"
                            Text { text: "DT"; color: "white" }
                            SpinBox { from: 60000; to: 60099; value: seqEditor ? seqEditor.selectedDatAddress : 60000
                                      onValueModified: seqEditor.setDatAddress(value) }
                            ComboBox { model: ["대입 (=)", "가산 (+=)", "감산 (-=)"]
                                       currentIndex: seqEditor ? seqEditor.selectedDatOp : 0
                                       onActivated: seqEditor.setDatOp(currentIndex) }
                            SpinBox { from: -32768; to: 32767; editable: true
                                      value: seqEditor ? seqEditor.selectedDatConst : 0
                                      onValueModified: seqEditor.setDatConst(value) }
                        }
                        Item { Layout.preferredHeight: 20 }
                    }
                }
            }
        }

        Flow {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: ["POS", "OUT", "IN", "TMR", "JMP", "CALL", "DAT", "END", "COMMENT"]
                Button { text: "+ " + modelData; width: 108; height: 46; onClicked: seqEditor.addStep(modelData) }
            }
        }
    }
}
