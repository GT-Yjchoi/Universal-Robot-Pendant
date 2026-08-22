import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string title: "순서 변경"
    property var values: []
    signal accepted(var values)
    signal rejected()
    function openValues(items) { values=items.slice(0); list.model=values; open() }
    modal:true; focus:true; closePolicy:Popup.NoAutoClose
    anchors.centerIn:Overlay.overlay; width:520; height:620
    Overlay.modal:Rectangle { color:"#a0000000" }
    background:Rectangle { color:"#17212c"; radius:14; border.color:"#468cff"; border.width:2 }
    contentItem:ColumnLayout {
        spacing:10
        Text { Layout.fillWidth:true; text:popup.title; color:"#ffd280"; font.pixelSize:23; font.bold:true; horizontalAlignment:Text.AlignHCenter }
        ListView {
            id:list; Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:6
            delegate:Rectangle {
                required property int index; required property var modelData
                width:ListView.view.width; height:62; radius:8; color:"#263441"; border.color:"#526578"
                RowLayout { anchors.fill:parent; anchors.margins:6
                    Text { Layout.fillWidth:true; text:(index+1)+". "+String(modelData); color:"white"; font.pixelSize:17; elide:Text.ElideRight }
                    PendantButton { Layout.preferredWidth:58; text:"▲"; enabled:index>0; onClicked:{ var a=popup.values.slice(0),v=a[index]; a[index]=a[index-1]; a[index-1]=v; popup.values=a; list.model=a } }
                    PendantButton { Layout.preferredWidth:58; text:"▼"; enabled:index<popup.values.length-1; onClicked:{ var a=popup.values.slice(0),v=a[index]; a[index]=a[index+1]; a[index+1]=v; popup.values=a; list.model=a } }
                }
            }
            ScrollBar.vertical:ScrollBar{}
        }
        RowLayout { Layout.fillWidth:true
            PendantButton { Layout.fillWidth:true; text:"취소"; accent:"#a75050"; onClicked:{popup.close();popup.rejected()} }
            PendantButton { Layout.fillWidth:true; text:"적용"; accent:"#468cff"; onClicked:{var out=popup.values.slice(0);popup.close();popup.accepted(out)} }
        }
    }
}
