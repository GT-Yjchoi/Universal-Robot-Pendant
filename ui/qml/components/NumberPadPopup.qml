import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    objectName: "numberPadPopup"
    property string title: "값 입력"
    property bool decimal: false
    property bool signed: false
    property bool password: false
    property real minimum: -999999999
    property real maximum: 999999999
    property bool replaceOnNextInput: false
    property alias text: editor.text
    signal accepted(real value)
    signal rejected()
    function openValue(value) {
        editor.text = password ? "" : (decimal ? Number(value).toFixed(2) : String(Math.round(value)))
        replaceOnNextInput = !password && editor.text.length > 0
        open()
        editor.forceActiveFocus()
    }
    function inputKey(key) {
        if (key === "⌫") {
            replaceOnNextInput = false
            editor.text = editor.text.slice(0, -1)
            return
        }
        if (replaceOnNextInput) {
            editor.text = ""
            replaceOnNextInput = false
        }
        if (key === "±") {
            editor.text = editor.text.startsWith("-") ? editor.text.slice(1) : "-" + editor.text
        } else if (key === ".") {
            if (editor.text.indexOf(".") < 0)
                editor.text = editor.text.length > 0 ? editor.text + "." : "0."
        } else {
            editor.text += key
        }
    }
    modal: true; focus: true; closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay; width: 390; height: 500
    Overlay.modal: Rectangle { color: "#a0000000" }
    background: Rectangle { color: "#19222d"; radius: 14; border.color: "#468cff"; border.width: 2 }
    contentItem: ColumnLayout {
        spacing: 10
        Text { Layout.fillWidth: true; text: popup.title; color: "#e9eef3"; font.pixelSize: 22; font.bold: true; horizontalAlignment: Text.AlignHCenter }
        TextField {
            id: editor; objectName: "numberPadEditor"; Layout.fillWidth: true; Layout.preferredHeight: 64
            color: "#e9eef3"; selectionColor: "#468cff"; selectedTextColor: "#ffffff"
            placeholderTextColor: "#6f7d8c"; font.pixelSize: 34; font.bold: true
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            echoMode: popup.password ? TextInput.Password : TextInput.Normal
            inputMethodHints: popup.decimal ? Qt.ImhFormattedNumbersOnly : Qt.ImhDigitsOnly
            onTextEdited: popup.replaceOnNextInput = false
            background: Rectangle {
                color: "#101821"; radius: 8
                border.color: editor.activeFocus ? "#468cff" : "#465564"
                border.width: editor.activeFocus ? 2 : 1
            }
        }
        GridLayout {
            columns: 3; Layout.fillWidth: true; Layout.fillHeight: true
            rowSpacing: 8; columnSpacing: 8
            uniformCellWidths: true; uniformCellHeights: true
            Repeater {
                model: ["7","8","9","4","5","6","1","2","3", popup.signed?"±":".","0","⌫"]
                PendantButton {
                    required property string modelData
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.preferredWidth: 1; Layout.preferredHeight: 1
                    text: modelData
                    enabled: modelData!=="." || popup.decimal
                    onClicked: popup.inputKey(modelData)
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            PendantButton { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "취소"; accent: "#b65252"; onClicked: { popup.close(); popup.rejected() } }
            PendantButton { Layout.fillWidth: true; Layout.preferredWidth: 1; text: "적용"; accent: "#468cff"; onClicked: { var raw=editor.text.trim(); if(raw.length===0) return; var v=Number(raw); if(isFinite(v)&&v>=popup.minimum&&v<=popup.maximum){ popup.close(); popup.accepted(v) } } }
        }
    }
}
