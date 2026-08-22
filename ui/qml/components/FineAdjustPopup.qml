import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id:popup
    property string title:"Fine Adjust"
    property real value:0
    property real minimum:0
    property real maximum:1000
    signal adjusted(real delta)
    signal dismissed()
    function openValue(v,lo,hi){value=v;minimum=lo;maximum=hi;open()}
    modal:true;focus:true;closePolicy:Popup.NoAutoClose;anchors.centerIn:Overlay.overlay;width:620;height:320
    Overlay.modal:Rectangle{color:"#a0000000"}
    background:Rectangle{color:"#17212c";radius:14;border.color:"#468cff";border.width:2}
    contentItem:ColumnLayout{
        spacing:14
        Text{Layout.fillWidth:true;text:popup.title;color:"#ffd280";font.pixelSize:22;font.bold:true;horizontalAlignment:Text.AlignHCenter}
        Text{Layout.fillWidth:true;text:Number(popup.value).toFixed(3)+" mm";color:"#64ffda";font.pixelSize:38;font.bold:true;horizontalAlignment:Text.AlignHCenter}
        Text{Layout.fillWidth:true;text:"범위: "+popup.minimum.toFixed(3)+" ~ "+popup.maximum.toFixed(3)+" mm";color:"#aaa";font.pixelSize:14;horizontalAlignment:Text.AlignHCenter}
        RowLayout{Layout.fillWidth:true;spacing:7
            Repeater{model:[-10,-1,-0.1,0.1,1,10]
                PendantButton{required property real modelData;Layout.fillWidth:true;text:(modelData>0?"+":"")+modelData;accent:modelData>0?"#318a65":"#a75050";onClicked:popup.adjusted(modelData)}
            }
        }
        PendantButton{Layout.fillWidth:true;text:"닫기";accent:"#667788";onClicked:{popup.close();popup.dismissed()}}
    }
}
