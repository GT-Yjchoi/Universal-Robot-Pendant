import QtQuick 2.15
import QtQuick.Controls 2.15
import "components"

Rectangle {
    color: "transparent"

    AlarmPanel {
        anchors.fill:parent; visible:overlayBackend.alarmVisible
        title:overlayBackend.alarmTitle; message:overlayBackend.alarmMessage
        accent:overlayBackend.alarmColor; resetVisible:overlayBackend.alarmResetVisible
        closeVisible:overlayBackend.alarmCloseVisible; pageText:overlayBackend.alarmPage
        multiple:overlayBackend.alarmMultiple
        onResetPressed:overlayBackend.resetPressed(); onResetReleased:overlayBackend.resetReleased()
        onCloseRequested:overlayBackend.closeAlarm(); onPreviousRequested:overlayBackend.previousAlarm(); onNextRequested:overlayBackend.nextAlarm()
    }
    JogPanel {
        visible:overlayBackend.jogVisible; anchors.top:parent.top; anchors.bottom:parent.bottom
        anchors.right:parent.right; anchors.margins:8; speed:overlayBackend.jogSpeed
        valves:overlayBackend.jogValves
        onCloseRequested:overlayBackend.closeJog()
        onAxisChanged:function(name,active){ overlayBackend.jogAxis(name,active) }
        onSpeedSelected:function(speed){ overlayBackend.setJogSpeed(speed) }
        onValveChanged:function(index,active){ overlayBackend.setJogValve(index,active) }
    }

    NumberPadPopup {
        id: numberPad
        onAccepted: function(value) { overlayBackend.acceptNumber(value) }
        onRejected: overlayBackend.rejectNumber()
    }
    ConfirmPopup {
        id: message
        rejectText: ""
        onAccepted: overlayBackend.closeMessage()
        onRejected: overlayBackend.closeMessage()
    }
    ReorderPopup {
        id: reorder
        onAccepted:function(values){ overlayBackend.acceptReorder(values) }
        onRejected:overlayBackend.rejectReorder()
    }
    TextKeyboardPopup {
        id: textKeyboard
        onAccepted:function(value){ overlayBackend.acceptText(value) }
        onRejected:overlayBackend.rejectText()
    }
    CardSelectorPopup {
        id:selector
        onSelected:function(index,value){overlayBackend.acceptSelection(index,value)}
        onRejected:overlayBackend.rejectSelection()
    }
    FineAdjustPopup {
        id:fine
        onAdjusted:function(delta){overlayBackend.adjustFine(delta)}
        onDismissed:overlayBackend.closeFine()
    }
    HistoryPopup {
        id: history
        onDismissed: overlayBackend.closeHistory()
    }
    ConfirmPopup {
        id: confirm
        onAccepted: overlayBackend.resolveConfirm(true)
        onRejected: overlayBackend.resolveConfirm(false)
    }
    Connections {
        target: overlayBackend
        function onNumberRequested(title, value, decimal, signed, minimum, maximum, password) {
            numberPad.title=title; numberPad.decimal=decimal; numberPad.signed=signed
            numberPad.minimum=minimum; numberPad.maximum=maximum; numberPad.password=password
            numberPad.openValue(value)
        }
        function onMessageRequested(title, body, error) {
            message.title=title; message.message=body
            message.acceptText="확인"; message.open()
        }
        function onConfirmRequested(title, body, acceptText, rejectText) {
            confirm.title=title; confirm.message=body
            confirm.acceptText=acceptText; confirm.rejectText=rejectText; confirm.open()
        }
        function onReorderRequested(title, values) {
            reorder.title=title; reorder.openValues(values)
        }
        function onTextRequested(title, value, password) {
            textKeyboard.title=title; textKeyboard.password=password; textKeyboard.openText(value)
        }
        function onSelectRequested(title, values, current) {
            selector.title=title; selector.items=values; selector.open()
        }
        function onFineRequested(title, value, minimum, maximum) {
            fine.title=title; fine.openValue(value,minimum,maximum)
        }
        function onHistoryRequested(alarms, operations) {
            history.alarmRows=alarms; history.operationRows=operations
            history.alarmTab=true; history.open()
        }
    }
    Connections { target:overlayBackend; function onFineValueUpdated(value){fine.value=value} }
}
