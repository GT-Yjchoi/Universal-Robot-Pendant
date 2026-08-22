import QtQuick 2.15

Rectangle {
    id: toast
    property string message: ""
    property int duration: 1800
    signal finished()
    visible: opacity > 0; opacity: 0; radius: 9; color: "#e6121720"; border.color: "#468cff"
    width: Math.min(implicitWidth, parent ? parent.width-40 : implicitWidth); height: 58
    implicitWidth: label.implicitWidth+44
    Text { id:label; anchors.centerIn:parent; text:toast.message; color:"white"; font.pixelSize:17; font.bold:true; elide:Text.ElideRight; width:Math.min(implicitWidth,toast.width-30); horizontalAlignment:Text.AlignHCenter }
    Behavior on opacity { NumberAnimation { duration: 160 } }
    Timer { id:timer; interval:toast.duration; onTriggered:{ toast.opacity=0; toast.finished() } }
    function show(text) { message=text; opacity=1; timer.restart() }
}
