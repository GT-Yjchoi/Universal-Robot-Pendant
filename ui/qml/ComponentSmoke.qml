import QtQuick 2.15
import QtQuick.Controls 2.15
import "components"

Rectangle {
    width: 1280; height: 720; color: "#101720"
    TopBar { anchors.top:parent.top; anchors.left:parent.left; anchors.right:parent.right; connected:true }
    BottomNav { anchors.bottom:parent.bottom; anchors.left:parent.left; anchors.right:parent.right }
    ConfirmPopup { id:confirm }
    NumberPadPopup { id:numpad }
    CardSelectorPopup { id:cards }
    Toast { anchors.horizontalCenter:parent.horizontalCenter; anchors.bottom:parent.bottom; anchors.bottomMargin:90 }
}
