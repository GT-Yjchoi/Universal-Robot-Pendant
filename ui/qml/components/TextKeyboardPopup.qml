import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup
    property string title: "텍스트 입력"
    property bool password: false
    property bool shifted: false
    signal accepted(string value)
    signal rejected()
    function openText(value) { editor.text=value; shifted=false; open(); editor.forceActiveFocus() }
    modal:true; focus:true; closePolicy:Popup.NoAutoClose
    anchors.centerIn:Overlay.overlay; width:900; height:500
    Overlay.modal:Rectangle{color:"#a0000000"}
    background:Rectangle{color:"#17212c";radius:14;border.color:"#468cff";border.width:2}
    contentItem:ColumnLayout{
        spacing:9
        Text{Layout.fillWidth:true;text:popup.title;color:"#ffd280";font.pixelSize:22;font.bold:true;horizontalAlignment:Text.AlignHCenter}
        TextField{id:editor;Layout.fillWidth:true;Layout.preferredHeight:62;color:"#f1c40f";font.pixelSize:28;echoMode:popup.password?TextInput.Password:TextInput.Normal}
        Repeater{
            model:[["1","2","3","4","5","6","7","8","9","0"],["q","w","e","r","t","y","u","i","o","p"],["a","s","d","f","g","h","j","k","l","-"],["z","x","c","v","b","n","m","_",".","⌫"]]
            RowLayout{
                required property var modelData;Layout.fillWidth:true;spacing:6
                Repeater{model:parent.modelData
                    PendantButton{required property string modelData;Layout.fillWidth:true;text:popup.shifted&&modelData.length===1?modelData.toUpperCase():modelData;onClicked:{if(modelData==="⌫")editor.text=editor.text.slice(0,-1);else editor.text+=text}}
                }
            }
        }
        RowLayout{Layout.fillWidth:true
            PendantButton{Layout.preferredWidth:130;text:popup.shifted?"ABC":"abc";onClicked:popup.shifted=!popup.shifted}
            PendantButton{Layout.fillWidth:true;text:"SPACE";onClicked:editor.text+=" "}
            PendantButton{Layout.preferredWidth:150;text:"취소";accent:"#a75050";onClicked:{popup.close();popup.rejected()}}
            PendantButton{Layout.preferredWidth:150;text:"적용";accent:"#468cff";onClicked:{var out=editor.text;popup.close();popup.accepted(out)}}
        }
    }
}
