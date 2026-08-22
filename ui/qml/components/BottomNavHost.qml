import QtQuick 2.15
import QtQuick.Controls 2.15

BottomNav {
    labels: navBackend ? navBackend.labels : []
    currentIndex: navBackend ? navBackend.currentIndex : 0
    onSelected: function(index) { if (navBackend) navBackend.choose(index) }
}
