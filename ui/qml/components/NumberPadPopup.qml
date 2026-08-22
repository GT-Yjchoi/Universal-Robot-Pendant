import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string title: "값 입력"
    property bool decimal: false
    property bool signed: false
    property bool password: false
    property real minimum: -999999999
    property real maximum: 999999999
    property alias text: editor.text
    signal accepted(real value)
    signal rejected()
    function openValue(value) { editor.text=decimal?Number(value).toFixed(2):String(Math.round(value)); open(); editor.forceActiveFocus() }
    modal: true; focus: true; closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay; width: 390; height: 500
    Overlay.modal: Rectangle { color: "#a0000000" }
    background: Rectangle { color: "#19222d"; radius: 14; border.color: "#468cff"; border.width: 2 }
    contentItem: ColumnLayout {
        spacing: 10
        Text { Layout.fillWidth: true; text: popup.title; color: "#ffd280"; font.pixelSize: 22; font.bold: true; horizontalAlignment: Text.AlignHCenter }
        TextField {
            id: editor; Layout.fillWidth: true; Layout.preferredHeight: 64
            color: "#f1c40f"; font.pixelSize: 34; horizontalAlignment: Text.AlignHCenter
            echoMode: popup.password ? TextInput.Password : TextInput.Normal
            inputMethodHints: popup.decimal ? Qt.ImhFormattedNumbersOnly : Qt.ImhDigitsOnly
        }
        GridLayout {
            columns: 3; Layout.fillWidth: true; Layout.fillHeight: true; rowSpacing: 7; columnSpacing: 7
            Repeater {
                model: ["1","2","3","4","5","6","7","8","9", popup.signed?"±":".","0","⌫"]
                PendantButton {
                    required property string modelData
                    Layout.fillWidth: true; Layout.fillHeight: true; text: modelData
                    enabled: modelData!=="." || popup.decimal
                    onClicked: {
                        if(modelData==="⌫") editor.text=editor.text.slice(0,-1)
                        else if(modelData==="±") editor.text=editor.text.startsWith("-")?editor.text.slice(1):"-"+editor.text
                        else if(modelData!=="." || editor.text.indexOf(".")<0) editor.text+=modelData
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            PendantButton { Layout.fillWidth: true; text: "취소"; accent: "#b65252"; onClicked: { popup.close(); popup.rejected() } }
            PendantButton { Layout.fillWidth: true; text: "적용"; accent: "#468cff"; onClicked: { var v=Number(editor.text); if(isFinite(v)&&v>=popup.minimum&&v<=popup.maximum){ popup.close(); popup.accepted(v) } } }
        }
    }
}
