import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    property bool connected: false
    property string recipeName: "No Data"
    property string modeText: "모드: 정지"
    property color modeColor: "#95a5a6"
    property string alarmText: ""
    signal jogRequested()
    signal alarmRequested()
    color: "#18212c"
    radius: 10
    border.color: "#344353"
    implicitHeight: 68

    Row {
        id: companyBlock
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 7

        Image {
            source: "../../../gtlogo.png"
            width: 38
            height: 34
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            smooth: true
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "AUTOMATION"
            color: "#f0f4f8"
            font.pixelSize: 21
            font.bold: true
            font.letterSpacing: 1
        }
    }

    Row {
        id: statusBlock
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        spacing: 16

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 7

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 11
                height: 11
                radius: 6
                color: root.connected ? "#42e878" : "#ff5252"
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.connected ? "PLC 연결" : "PLC 끊김"
                color: root.connected ? "#72f29a" : "#ff7777"
                font.pixelSize: 15
                font.bold: true
            }
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 24
            color: "#526170"
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.modeText
            color: root.modeColor
            font.pixelSize: 16
            font.bold: true
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 24
            color: "#526170"
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "레시피: " + root.recipeName
            color: "#ffd280"
            font.pixelSize: 16
            font.bold: true
        }
    }

    Row {
        id: rightBlock
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10

        Text {
            id: clock
            anchors.verticalCenter: parent.verticalCenter
            color: "#dce5ee"
            font.pixelSize: 16
            font.bold: true

            function update() {
                text = Qt.formatDateTime(new Date(), "yyyy/MM/dd  HH:mm")
            }

            Component.onCompleted: update()

            Timer {
                interval: 1000
                running: true
                repeat: true
                onTriggered: clock.update()
            }
        }

        PendantButton {
            width: 82
            height: 44
            text: "JOG"
            accent: "#468cff"
            onClicked: root.jogRequested()
        }

        PendantButton {
            visible: root.alarmText !== ""
            width: visible ? Math.max(96, implicitWidth) : 0
            height: 44
            text: root.alarmText
            accent: "#d9534f"
            onClicked: root.alarmRequested()
        }
    }
}
