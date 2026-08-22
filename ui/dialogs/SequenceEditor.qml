import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    color: "#0F161E"
    property color panel: "#17222E"
    property color borderCol: "#35506A"

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 14; spacing: 10
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 54
            Text { text: "시퀀스 편집 (QML)"; color: "#65A1FF"; font.pixelSize: 24; font.bold: true }
            ComboBox {
                Layout.preferredWidth: 260; model: seqEditor ? seqEditor.sequenceKeys : []
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
                Layout.preferredWidth: 440; Layout.fillHeight: true; color: panel; radius: 10
                border.color: borderCol
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 10; spacing: 8
                    ListView {
                        id: list; Layout.fillWidth: true; Layout.fillHeight: true
                        model: stepModel; clip: true; spacing: 5
                        boundsBehavior: Flickable.StopAtBounds
                        delegate: Rectangle {
                            width: list.width; height: 54; radius: 7
                            color: index === (seqEditor ? seqEditor.selectedRow : -1) ? "#354F6B" : "#202F3E"
                            border.color: model.stepColor; border.width: index === seqEditor.selectedRow ? 2 : 1
                            Row {
                                anchors.fill: parent; anchors.margins: 8; spacing: 10
                                Rectangle { width: 8; height: parent.height; radius: 4; color: model.stepColor }
                                Text { width: parent.width - 26; anchors.verticalCenter: parent.verticalCenter
                                       text: (index + 1) + ". " + model.summary; color: "white";
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
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 18; spacing: 14
                    Text { text: seqEditor && seqEditor.selectedType ? seqEditor.selectedType + " 스텝" : "스텝을 선택하세요"
                           color: "#65A1FF"; font.pixelSize: 23; font.bold: true }
                    TextField {
                        Layout.fillWidth: true; placeholderText: "이름 / 메모"
                        text: seqEditor ? seqEditor.selectedName : ""
                        enabled: seqEditor && seqEditor.selectedType !== ""
                        onEditingFinished: seqEditor.setName(text)
                    }
                    RowLayout {
                        visible: seqEditor && (seqEditor.selectedType === "OUT" || seqEditor.selectedType === "IN")
                        Text { text: "DIO 채널"; color: "white"; font.pixelSize: 19 }
                        Button { text: "−"; onClicked: seqEditor.setChannel(seqEditor.selectedChannel - 1) }
                        Text { text: seqEditor ? seqEditor.selectedChannel : 0; color: "#FFD166"; font.pixelSize: 28; font.bold: true }
                        Button { text: "+"; onClicked: seqEditor.setChannel(seqEditor.selectedChannel + 1) }
                        Item { Layout.fillWidth: true }
                        Button { text: seqEditor && seqEditor.selectedOn ? "ON" : "OFF"; highlighted: seqEditor && seqEditor.selectedOn
                                 onClicked: seqEditor.setOn(!seqEditor.selectedOn) }
                    }
                    RowLayout {
                        visible: seqEditor && seqEditor.selectedType === "TMR"
                        Text { text: "시간"; color: "white"; font.pixelSize: 19 }
                        Button { text: "−0.1"; onClicked: seqEditor.setSeconds(seqEditor.selectedSeconds - 0.1) }
                        Text { text: (seqEditor ? seqEditor.selectedSeconds : 0).toFixed(3) + " s"; color: "#FFD166"; font.pixelSize: 28 }
                        Button { text: "+0.1"; onClicked: seqEditor.setSeconds(seqEditor.selectedSeconds + 0.1) }
                    }
                    ComboBox {
                        Layout.fillWidth: true; visible: seqEditor && seqEditor.selectedType === "JMP"
                        model: seqEditor ? seqEditor.stepTargets : []; currentIndex: seqEditor ? seqEditor.selectedTargetIndex : 0
                        onActivated: seqEditor.setTargetIndex(currentIndex)
                    }
                    ComboBox {
                        Layout.fillWidth: true; visible: seqEditor && seqEditor.selectedType === "CALL"
                        model: seqEditor ? seqEditor.targetSequenceKeys : []; currentIndex: seqEditor ? seqEditor.targetSequenceIndex : -1
                        onActivated: seqEditor.setTargetSequenceIndex(currentIndex)
                    }
                    Item { Layout.fillHeight: true }
                    Text { text: "DIO 모드 지원: OUT · IN · TMR · JMP · CALL · END"; color: "#9FB3C8"; font.pixelSize: 15 }
                }
            }
        }

        Flow {
            Layout.fillWidth: true; spacing: 8
            Repeater {
                model: ["OUT", "IN", "TMR", "JMP", "CALL", "END", "COMMENT"]
                Button { text: "+ " + modelData; width: 120; height: 48; onClicked: seqEditor.addStep(modelData) }
            }
        }
    }
}
