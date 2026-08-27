import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root
    objectName: "bottomBarSurface"
    property int currentIndex: 0
    property var labels: ["수동","자동","모드","위치","타이머","패킹","데이터","설정"]
    signal selected(int index)
    implicitHeight:70

    Row { anchors.fill:parent; anchors.margins:8; spacing:8
        Repeater { model:root.labels
            PendantButton {
                required property int index
                required property string modelData
                width: root.labels.length > 0 ? (parent.width - parent.spacing * (root.labels.length - 1)) / root.labels.length : 0
                height: parent.height
                text: modelData
                accent: index === root.currentIndex ? "#468cff" : "#53606d"
                onClicked: root.selected(index)
            }
        }
    }
}
