import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import "components"
import "../pages" as Pages
import "../dialogs" as Dialogs

ApplicationWindow {
    id: root
    objectName: "pendantWindow"
    width: 1280
    height: 800
    visible: true
    visibility: Window.FullScreen
    flags: Qt.FramelessWindowHint
    title: "Universal Robot Pendant"
    color: "#18232E"
    readonly property bool sequenceEditorActive: sequenceSession
                                                 ? sequenceSession.visible
                                                 : false

    Rectangle {
        anchors.fill: parent
        visible: !root.sequenceEditorActive
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#1a2733" }
            GradientStop { position: 0.45; color: "#1b2430" }
            GradientStop { position: 1.0; color: "#0f161e" }
        }
    }

    ColumnLayout {
        id: mainChrome
        objectName: "mainChrome"
        anchors.fill: parent
        anchors.topMargin: 0
        anchors.bottomMargin: 10
        spacing: 12
        visible: !root.sequenceEditorActive
        enabled: visible

        Rectangle {
            id: topBarPanel
            objectName: "topBarPanel"
            Layout.fillWidth: true
            Layout.preferredHeight: 60
            color: "#090f16"
            radius: 0
            border.width: 0

            TopBarHost {
                anchors.fill: parent
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 16
            Layout.rightMargin: 16
            clip: true

            StackLayout {
                id: pageStack
                objectName: "pageStack"
                anchors.fill: parent
                currentIndex: navBackend ? navBackend.currentIndex : 0

                Pages.PageManual {
                    axisModel: manualAxisModel
                    ioInModel: manualIoInModel
                    ioOutModel: manualIoOutModel
                    valveModel: manualValveModel
                    ioBackend: manualIoBackend
                    valveBackend: manualValveBackend
                }
                Pages.PageAuto {
                    axisModel: autoAxisModel
                    ioInModel: autoIoInModel
                    ioOutModel: autoIoOutModel
                    ioBackend: autoIoBackend
                    autoBackend: autoPageBackend
                }
                Pages.PageMode {
                    modeModel: modePageModel
                    backend: modeBackend
                }
                Pages.PagePosition {
                    axisModel: positionAxisModel
                    previewModel: positionPreviewModel
                    valveModel: positionValveModel
                    valveBackend: positionValveBackend
                    posBackend: positionBackend
                }
                Pages.PageTimer {
                    timerModel: timerPageModel
                    timerBackend: timerPageBackend
                }
                Pages.PagePacking {
                    packingBackend: packingPageBackend
                }
                Pages.PageData {
                    fileModel: dataFileModel
                    previewModel: dataPreviewModel
                    dataBackend: dataPageBackend
                }
                Pages.PageSettings {
                    ioModel: settingsIoModel
                    paramModel: settingsParamModel
                    valveModel: settingsValveModel
                    alarmModel: settingsAlarmModel
                    wifiModel: settingsWifiModel
                    ilModeModel: settingsIlModeModel
                    ilGroupModel: settingsIlGroupModel
                    settingsBackend: settingsPageBackend
                }
            }
        }

        BottomNavHost {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            Layout.leftMargin: 16
            Layout.rightMargin: 16
        }
    }

    Rectangle {
        objectName: "sequenceEditorLayer"
        anchors.fill: parent
        visible: root.sequenceEditorActive
        enabled: visible
        z: 200
        color: "#18232E"
        opacity: 1.0
        clip: true

        Loader {
            anchors.fill: parent
            active: parent.visible
            asynchronous: false
            sourceComponent: Component {
                Dialogs.SequenceEditor {
                    seqEditor: sequenceSession.backend
                    stepModel: sequenceSession.model
                }
            }
        }
    }

    OverlayHost {
        anchors.fill: parent
        z: 300
    }
}
