pragma ComponentBehavior: Bound

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    required property var posBackend
    property var frozenPrograms: []

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: Math.min(1120, parent ? parent.width - 50 : 1120)
    height: Math.min(680, parent ? parent.height - 40 : 680)
    onOpened: {
        // Keep one stable model while the popup is open. Runtime events only
        // refresh highlight bindings, so the user's scroll position is kept.
        frozenPrograms = posBackend.monitorPrograms
        posBackend.setSequenceMonitorVisible(true)
    }
    onClosed: posBackend.setSequenceMonitorVisible(false)

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
                text: "전체 프로그램 실행 모니터"
                color: "#9CC8FF"
                font.pixelSize: 24
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Button {
                Layout.preferredWidth: 90
                Layout.preferredHeight: 42
                text: "닫기"
                contentItem: Text {
                    text: parent.text
                    color: "white"
                    font.pixelSize: 16
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: 7
                    color: parent.pressed ? "#A04747" : "#805050"
                    border.color: "#C66B6B"
                }
                onClicked: popup.close()
            }
        }
        Text {
            Layout.fillWidth: true
            text: "프로그램을 3열로 동시에 표시합니다. 각 카드의 스텝은 위아래로, 프로그램은 좌우로 이동합니다."
            color: "#91A5B8"
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
        }
        ListView {
            id: programStrip
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            orientation: ListView.Horizontal
            spacing: 8
            model: popup.frozenPrograms
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.horizontal: ScrollBar {
                policy: ScrollBar.AsNeeded
                height: 10
                contentItem: Rectangle {
                    radius: 6
                    color: parent.pressed ? "#7EB2FF" : "#527CA5"
                }
                background: Rectangle { color: "#101821"; radius: 6 }
            }

            delegate: Rectangle {
                id: programCard
                required property var modelData
                width: Math.max(250, (ListView.view.width - 16) / 3)
                height: ListView.view.height - 8
                radius: 9
                property int monitorRevision: popup.posBackend.monitorRevision
                property bool programRunning: {
                    var revisionDependency = monitorRevision
                    return popup.posBackend.isSequenceRunning(String(modelData.program))
                }
                color: "#18242F"
                border.width: programRunning ? 2 : 1
                border.color: programRunning ? "#00E5FF" : "#304557"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 5

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        radius: 7
                        color: programCard.programRunning ? "#29465C" : "#202D3A"
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 9
                            spacing: 7
                            Rectangle {
                                Layout.preferredWidth: 58
                                Layout.preferredHeight: 27
                                radius: 5
                                color: String(programCard.modelData.kind) === "MAIN"
                                       ? "#174D41" : "#332F57"
                                Text {
                                    anchors.centerIn: parent
                                    text: String(programCard.modelData.kind)
                                    color: String(programCard.modelData.kind) === "MAIN"
                                           ? "#64FFDA" : "#B9B1FF"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: String(programCard.modelData.program)
                                color: "white"
                                font.pixelSize: 17
                                font.bold: true
                                elide: Text.ElideRight
                                horizontalAlignment: Text.AlignHCenter
                            }
                            Text {
                                Layout.preferredWidth: 34
                                text: programCard.programRunning ? "RUN" : ""
                                color: "#00E5FF"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                    }

                    ListView {
                        id: programSteps
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 3
                        model: programCard.modelData.steps
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            width: 9
                            contentItem: Rectangle {
                                radius: 4
                                color: parent.pressed ? "#7EB2FF" : "#527CA5"
                            }
                        }
                        delegate: Rectangle {
                            id: stepRow
                            required property var modelData
                            width: ListView.view.width
                            height: 40
                            radius: 4
                            property int monitorRevision: programCard.monitorRevision
                            property bool liveActive: {
                                var revisionDependency = monitorRevision
                                return Number(modelData.stepIndex) >= 0
                                    && popup.posBackend.isSequenceStepActive(
                                    String(programCard.modelData.program),
                                    Number(modelData.stepIndex))
                            }
                            color: liveActive ? "#334F67" : "#192630"
                            border.width: liveActive ? 2 : 1
                            border.color: liveActive ? "#00E5FF" : "#304557"
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 6
                                Rectangle {
                                    Layout.preferredWidth: 4
                                    Layout.fillHeight: true
                                    radius: 2
                                    color: stepRow.liveActive ? "#00E5FF" : "transparent"
                                }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    text: String(stepRow.modelData.text)
                                    color: Boolean(stepRow.modelData.comment) ? "#FFD166"
                                           : stepRow.liveActive ? "#FFFFFF" : "#C3CED8"
                                    font.pixelSize: 14
                                    font.bold: stepRow.liveActive
                                    font.italic: Boolean(stepRow.modelData.comment)
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
