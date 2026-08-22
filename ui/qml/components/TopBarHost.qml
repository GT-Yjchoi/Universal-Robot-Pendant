import QtQuick 2.15
import QtQuick.Controls 2.15

TopBar {
    connected: topBackend ? topBackend.connected : false
    recipeName: topBackend ? topBackend.recipeName : ""
    modeText: topBackend ? topBackend.modeText : "STOP"
    modeColor: topBackend ? topBackend.modeColor : "#aaaaaa"
    alarmText: topBackend ? topBackend.alarmText : ""
    onJogRequested: if (topBackend) topBackend.requestJog()
    onAlarmRequested: if (topBackend) topBackend.requestAlarm()
}
