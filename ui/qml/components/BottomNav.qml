import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property int currentIndex: 0
    property var labels: ["수동","자동","모드","위치","타이머","패킹","데이터","설정"]
    signal selected(int index)
    color:"#18212c"; radius:10; border.color:"#344353"; implicitHeight:70
    RowLayout { anchors.fill:parent; anchors.margins:8; spacing:8
        Repeater { model:root.labels
            PendantButton { required property int index; required property string modelData; Layout.fillWidth:true; Layout.fillHeight:true; text:modelData; accent:index===root.currentIndex?"#468cff":"#53606d"; onClicked:root.selected(index) }
        }
    }
}
