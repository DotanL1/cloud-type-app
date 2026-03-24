import QtQuick
import QtQuick.Controls
import Qt5Compat.GraphicalEffects

Item {
    id: root
    width: 260
    height: 260

    property url iconSource: ""
    property string label: ""
    signal clicked()

    property bool hovered: mouse.containsMouse

    Rectangle {
        id: cardBg
        anchors.fill: parent
        radius: 18
        color: "#2e2e2e"
        opacity: 0.0

        Rectangle {
            anchors.fill: parent
            radius: cardBg.radius
            color: "white"
            opacity: root.hovered ? 0.08 : 0.0
            Behavior on opacity { NumberAnimation { duration: 150 } }
        }

        layer.enabled: true
        layer.effect: DropShadow {
            horizontalOffset: 0
            verticalOffset: root.hovered ? 18 : 6
            radius: root.hovered ? 40 : 18
            samples: 64
            color: "#80000000"
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 12

        Item {
            width: 140
            height: 140

            Image {
                anchors.fill: parent
                source: root.iconSource
                fillMode: Image.PreserveAspectFit
                cache: false
            }
        }

        Text {
            text: root.label
            color: "white"
            font.pixelSize: 18
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            width: 200
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    states: [
        State {
            name: "hover"
            when: root.hovered
            PropertyChanges { target: root; scale: 1.06 }
            PropertyChanges { target: root; y: -6 }
            PropertyChanges { target: cardBg; opacity: 1.0 }
        },
        State {
            name: "normal"
            when: !root.hovered
            PropertyChanges { target: root; scale: 1.0 }
            PropertyChanges { target: root; y: 0 }
            PropertyChanges { target: cardBg; opacity: 0.0 }
        }
    ]

    Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
    Behavior on y     { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
}