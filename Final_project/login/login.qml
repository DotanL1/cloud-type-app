import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects
import Qt.labs.platform 1.1

ApplicationWindow {
    id: win
    visible: true
    width: 1100
    height: 720
    minimumWidth: 900
    minimumHeight: 600
    title: "Dotan's Cloud"
    color: "#161618"

    onClosing: Backend.exit_app()

    FontLoader { id: roboto; source: "qrc:/fonts/Roboto-Regular.ttf" }

    // ─────────────────────────────────────────────────────────────────────
    //  Shared data models
    // ─────────────────────────────────────────────────────────────────────
    ListModel { id: cloudModel }       // all files from server
    ListModel { id: favoritesModel }   // client-side favorites (name)
    ListModel { id: recentModel }      // client-side recent (name, time)
    ListModel { id: sharedModel }      // files shared with current user

    property string actionMessage: ""
    property color actionMessageColor: "#4ade80"

    // helper: add to recent (dedup, cap 20)
    function addToRecent(fileName) {
        for (var i = 0; i < recentModel.count; i++) {
            if (recentModel.get(i).name === fileName) { recentModel.remove(i); break }
        }
        var now = new Date()
        var timeStr = now.getHours() + ":" + String(now.getMinutes()).padStart(2,"0")
        recentModel.insert(0, { name: fileName, time: timeStr })
        if (recentModel.count > 20) recentModel.remove(recentModel.count - 1)
    }

    function isFavorite(fileName) {
        for (var i = 0; i < favoritesModel.count; i++)
            if (favoritesModel.get(i).name === fileName) return true
        return false
    }

    function toggleFavorite(fileName) {
        for (var i = 0; i < favoritesModel.count; i++) {
            if (favoritesModel.get(i).name === fileName) { favoritesModel.remove(i); return }
        }
        favoritesModel.append({ name: fileName })
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Global backend connections
    // ─────────────────────────────────────────────────────────────────────
    Connections {
        target: Backend

        function onLogin_res(ok, msg) {
            loginStatus.text = ok ? "" : msg
            loginStatus.color = "#f87171"
            if (ok) {
                appStack.currentIndex = 1
                Backend.requestCloudFiles()
                Backend.requestSharedFiles()
            }
        }

        function onSigunp_res(ok, msg) {
            if (ok) {
                loginStatus.text = "Account created — please log in."
                loginStatus.color = "#4ade80"
                rightPanel.mode = "login"
            } else {
                loginStatus.text = msg
                loginStatus.color = "#f87171"
            }
        }

        function onCloud_list_res(files) {
            cloudModel.clear()
            for (var i = 0; i < files.length; i++)
                cloudModel.append({ name: files[i] })
            if (appStack.currentIndex !== 1) appStack.currentIndex = 1
        }

        function onShared_list_res(files) {
            sharedModel.clear()
            for (var i = 0; i < files.length; i++)
                sharedModel.append({ name: files[i].file_name, owner: files[i].owner, access: files[i].access })
        }

        function onAction_status(ok, msg) {
            actionMessage = msg
            actionMessageColor = ok ? "#4ade80" : "#f87171"
            Backend.requestSharedFiles()
        }

        function onLog_out() {
            cloudModel.clear()
            favoritesModel.clear()
            recentModel.clear()
            sharedModel.clear()
            appStack.currentIndex = 0
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    //  Page stack  (0 = auth, 1 = main app)
    // ─────────────────────────────────────────────────────────────────────
    StackLayout {
        id: appStack
        anchors.fill: parent
        currentIndex: 0

        // ═════════════════════════════════════════════════════════════════
        //  PAGE 0  ·  AUTH  (Login / Sign-up)
        // ═════════════════════════════════════════════════════════════════
        Item {
            id: authRoot

            Rectangle { anchors.fill: parent; color: "#161618" }

            // Subtle grid texture
            Canvas {
                anchors.fill: parent; opacity: 0.045
                onPaint: {
                    var ctx = getContext("2d")
                    ctx.strokeStyle = "#ffffff"
                    ctx.lineWidth = 0.5
                    for (var x = 0; x < width; x += 40) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,height); ctx.stroke() }
                    for (var y = 0; y < height; y += 40) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(width,y); ctx.stroke() }
                }
            }

            // Glow blob
            Rectangle {
                width: 500; height: 500; radius: 250
                color: "#4f46e5"; opacity: 0.07
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -80
            }

            // ── Auth card ─────────────────────────────────────────────
            Rectangle {
                id: authCard
                width: 440; height: 520; radius: 16
                color: "#1e1e20"
                border.color: "#2a2a2e"; border.width: 1
                opacity: 0
                anchors.centerIn: parent
                anchors.verticalCenterOffset: 30

                layer.enabled: true
                layer.effect: DropShadow { horizontalOffset: 0; verticalOffset: 20; radius: 60; samples: 64; color: "#60000000" }

                Component.onCompleted: authIntro.start()
                ParallelAnimation {
                    id: authIntro
                    NumberAnimation { target: authCard; property: "opacity"; to: 1; duration: 500; easing.type: Easing.OutCubic }
                    NumberAnimation { target: authCard; property: "anchors.verticalCenterOffset"; to: 0; duration: 600; easing.type: Easing.OutCubic }
                }

                // Brand header
                Column {
                    id: brandHeader
                    anchors.top: parent.top; anchors.topMargin: 36
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8

                    Row {
                        spacing: 10; anchors.horizontalCenter: parent.horizontalCenter
                        Rectangle {
                            width: 32; height: 32; radius: 8; color: "#4f46e5"
                            anchors.verticalCenter: parent.verticalCenter
                            Image { source: "qrc:/images/cloud.png"; width: 18; height: 18; fillMode: Image.PreserveAspectFit; anchors.centerIn: parent; opacity: 0.9 }
                        }
                        Text { text: "Dotan's Cloud"; color: "#f5f5f7"; font.family: roboto.name; font.pixelSize: 22; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                    }
                }

                // Status message
                Rectangle {
                    id: statusBanner
                    visible: loginStatus.text !== ""
                    anchors.top: brandHeader.bottom; anchors.topMargin: 16
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.leftMargin: 32; anchors.rightMargin: 32
                    height: 34; radius: 8
                    color: loginStatus.color === "#f87171" ? "#2a1515" : "#152a1e"
                    border.color: loginStatus.color === "#f87171" ? "#5a2020" : "#1f5a35"; border.width: 1
                    Text {
                        id: loginStatus; text: ""; color: "#f87171"; font.pixelSize: 13
                        anchors.centerIn: parent
                    }
                }

                // ── LOGIN FORM ────────────────────────────────────────
                Item {
                    id: loginPage
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; top: brandHeader.bottom }
                    anchors.topMargin: 8
                    opacity: rightPanel.mode === "login" ? 1 : 0
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: 200 } }

                    Column {
                        anchors.centerIn: parent; anchors.verticalCenterOffset: 10
                        spacing: 16; width: 340

                        Text { text: "Sign in"; color: "#f5f5f7"; font.family: roboto.name; font.pixelSize: 24; font.bold: true }

                        // Username
                        Column { spacing: 6; width: parent.width
                            Text { text: "Username"; color: "#888"; font.pixelSize: 12; font.family: roboto.name }
                            TextField {
                                id: lgUsername; width: parent.width; height: 42
                                color: "#f5f5f7"; placeholderText: "Enter username"; placeholderTextColor: "#444"
                                font.pixelSize: 14; leftPadding: 14; font.family: roboto.name
                                background: Rectangle {
                                    radius: 8; color: "#111113"
                                    border.color: lgUsername.activeFocus ? "#4f46e5" : "#2e2e32"; border.width: 1.5
                                    Behavior on border.color { ColorAnimation { duration: 150 } }
                                }
                                Keys.onReturnPressed: lgPassword.forceActiveFocus()
                            }
                        }

                        // Password
                        Column { spacing: 6; width: parent.width
                            Text { text: "Password"; color: "#888"; font.pixelSize: 12; font.family: roboto.name }
                            TextField {
                                id: lgPassword; width: parent.width; height: 42
                                color: "#f5f5f7"; placeholderText: "Enter password"; placeholderTextColor: "#444"
                                echoMode: TextInput.Password; font.pixelSize: 14; leftPadding: 14; font.family: roboto.name
                                background: Rectangle {
                                    radius: 8; color: "#111113"
                                    border.color: lgPassword.activeFocus ? "#4f46e5" : "#2e2e32"; border.width: 1.5
                                    Behavior on border.color { ColorAnimation { duration: 150 } }
                                }
                                Keys.onReturnPressed: { loginStatus.text = ""; Backend.login(lgUsername.text, lgPassword.text) }
                            }
                        }

                        // Sign in button
                        Rectangle {
                            width: parent.width; height: 42; radius: 8
                            color: lgBtnMa.containsPress ? "#3730a3" : (lgBtnMa.containsMouse ? "#5b52f0" : "#4f46e5")
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Text { text: "Sign in"; color: "#ffffff"; font.pixelSize: 15; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                            MouseArea { id: lgBtnMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { loginStatus.text = ""; Backend.login(lgUsername.text, lgPassword.text) } }
                        }

                        // Divider
                        Row { spacing: 10; anchors.horizontalCenter: parent.horizontalCenter; width: parent.width
                            Rectangle { width: (parent.width - 80) / 2; height: 1; color: "#2a2a2e"; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: "or"; color: "#555"; font.pixelSize: 12 }
                            Rectangle { width: (parent.width - 80) / 2; height: 1; color: "#2a2a2e"; anchors.verticalCenter: parent.verticalCenter }
                        }

                        Row {
                            spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                            Text { text: "Don't have an account?"; color: "#666"; font.pixelSize: 13; font.family: roboto.name }
                            Text {
                                text: "Sign up"; color: "#818cf8"; font.pixelSize: 13; font.family: roboto.name
                                MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { loginStatus.text = ""; rightPanel.mode = "signup" } }
                            }
                        }
                    }
                }

                // ── SIGNUP FORM ───────────────────────────────────────
                Item {
                    id: signupPage
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; top: brandHeader.bottom }
                    anchors.topMargin: 8
                    opacity: rightPanel.mode === "signup" ? 1 : 0
                    visible: opacity > 0
                    Behavior on opacity { NumberAnimation { duration: 200 } }

                    // Expand card when signup shown
                    Rectangle { id: rightPanel; property string mode: "login"; visible: false; width: 0; height: 0 }

                    Column {
                        anchors.centerIn: parent; anchors.verticalCenterOffset: 10
                        spacing: 14; width: 340

                        Text { text: "Create account"; color: "#f5f5f7"; font.family: roboto.name; font.pixelSize: 24; font.bold: true }

                        Row {
                            spacing: 10; width: parent.width
                            Column { spacing: 6; width: (parent.width - 10) / 2
                                Text { text: "Username"; color: "#888"; font.pixelSize: 12; font.family: roboto.name }
                                TextField {
                                    id: suUsername; width: parent.width; height: 42
                                    color: "#f5f5f7"; placeholderText: "Username"; placeholderTextColor: "#444"
                                    font.pixelSize: 14; leftPadding: 12; font.family: roboto.name
                                    background: Rectangle { radius: 8; color: "#111113"; border.color: suUsername.activeFocus ? "#4f46e5" : "#2e2e32"; border.width: 1.5; Behavior on border.color { ColorAnimation { duration: 150 } } }
                                }
                            }
                            Column { spacing: 6; width: (parent.width - 10) / 2
                                Text { text: "Email"; color: "#888"; font.pixelSize: 12; font.family: roboto.name }
                                TextField {
                                    id: suEmail; width: parent.width; height: 42
                                    color: "#f5f5f7"; placeholderText: "Email"; placeholderTextColor: "#444"
                                    font.pixelSize: 14; leftPadding: 12; font.family: roboto.name
                                    background: Rectangle { radius: 8; color: "#111113"; border.color: suEmail.activeFocus ? "#4f46e5" : "#2e2e32"; border.width: 1.5; Behavior on border.color { ColorAnimation { duration: 150 } } }
                                }
                            }
                        }

                        Column { spacing: 6; width: parent.width
                            Text { text: "Password"; color: "#888"; font.pixelSize: 12; font.family: roboto.name }
                            TextField {
                                id: suPassword; width: parent.width; height: 42
                                color: "#f5f5f7"; placeholderText: "Password"; placeholderTextColor: "#444"
                                echoMode: TextInput.Password; font.pixelSize: 14; leftPadding: 14; font.family: roboto.name
                                background: Rectangle { radius: 8; color: "#111113"; border.color: suPassword.activeFocus ? "#4f46e5" : "#2e2e32"; border.width: 1.5; Behavior on border.color { ColorAnimation { duration: 150 } } }
                            }
                        }

                        Rectangle {
                            width: parent.width; height: 42; radius: 8
                            color: suBtnMa.containsPress ? "#3730a3" : (suBtnMa.containsMouse ? "#5b52f0" : "#4f46e5")
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Text { text: "Create Account"; color: "#ffffff"; font.pixelSize: 15; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                            MouseArea { id: suBtnMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { loginStatus.text = ""; Backend.signup(suUsername.text, suEmail.text, suPassword.text) } }
                        }

                        Row {
                            spacing: 5; anchors.horizontalCenter: parent.horizontalCenter
                            Text { text: "Already have an account?"; color: "#666"; font.pixelSize: 13; font.family: roboto.name }
                            Text {
                                text: "Sign in"; color: "#818cf8"; font.pixelSize: 13; font.family: roboto.name
                                MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { loginStatus.text = ""; rightPanel.mode = "login" } }
                            }
                        }
                    }
                }
            }
        }

        // ═════════════════════════════════════════════════════════════════
        //  PAGE 1  ·  MAIN APP  (Sidebar + Content)
        // ═════════════════════════════════════════════════════════════════
        Item {
            id: mainRoot

            Rectangle { anchors.fill: parent; color: "#161618" }

            // ── Save / Open dialogs ──────────────────────────────────────
            FileDialog {
                id: saveDialog; title: "Save file as…"; fileMode: FileDialog.SaveFile
                property string pendingName: ""
                property string pendingOwner: ""
                onAccepted: {
                    var path = saveDialog.currentFile.toString()
                    if (path.startsWith("file:///")) path = decodeURIComponent(path.substring(8))
                    addToRecent(saveDialog.pendingName)
                    Backend.downloadCloudFileByOwner(saveDialog.pendingName, path, saveDialog.pendingOwner)
                }
            }
            FileDialog {
                id: openSaveDialog; title: "Choose where to save & open"; fileMode: FileDialog.SaveFile
                property string pendingName: ""
                property string pendingOwner: ""
                onAccepted: {
                    var path = openSaveDialog.currentFile.toString()
                    if (path.startsWith("file:///")) path = decodeURIComponent(path.substring(8))
                    addToRecent(openSaveDialog.pendingName)
                    Backend.downloadCloudFileByOwner(openSaveDialog.pendingName, path, openSaveDialog.pendingOwner)
                    Qt.openUrlExternally(openSaveDialog.currentFile)
                }
            }
            Popup {
                id: shareDialog
                modal: true
                property string pendingFileName: ""
                anchors.centerIn: parent
                width: 320
                height: 190
                padding: 18
                closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                background: Rectangle {
                    radius: 12
                    color: "#1e1e20"
                    border.color: "#2a2a2e"
                    border.width: 1
                }
                contentItem: Column {
                    spacing: 12
                    Text {
                        text: "Share file"
                        color: "#f5f5f7"
                        font.pixelSize: 18
                        font.bold: true
                        font.family: roboto.name
                    }
                    Text {
                        text: "Enter a username to share this file with."
                        color: "#888"
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        font.family: roboto.name
                    }
                    TextField {
                        id: shareUsername
                        width: parent.width
                        placeholderText: "Recipient username"
                    }
                    Row {
                        spacing: 10
                        Rectangle {
                            width: 96; height: 36; radius: 8
                            color: cancelShareMa.containsMouse ? "#26262a" : "#1a1a1d"
                            border.color: "#34343a"; border.width: 1
                            Text { text: "Cancel"; color: "#d4d4d8"; anchors.centerIn: parent; font.pixelSize: 13; font.family: roboto.name }
                            MouseArea {
                                id: cancelShareMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    shareUsername.text = ""
                                    shareDialog.close()
                                }
                            }
                        }
                        Rectangle {
                            width: 96; height: 36; radius: 8
                            color: saveShareMa.containsMouse ? "#24553a" : "#1d4731"
                            Text { text: "Share"; color: "#ecfdf5"; anchors.centerIn: parent; font.pixelSize: 13; font.bold: true; font.family: roboto.name }
                            MouseArea {
                                id: saveShareMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    var recipient = shareUsername.text.trim()
                                    if (recipient.length > 0)
                                        Backend.share_file(shareDialog.pendingFileName, recipient, "edit")
                                    shareUsername.text = ""
                                    shareDialog.close()
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                anchors.fill: parent
                spacing: 0

                // ── LEFT SIDEBAR ─────────────────────────────────────────
                Rectangle {
                    id: sidebar
                    Layout.preferredWidth: 220
                    Layout.fillHeight: true
                    color: "#111113"

                    // Right border line
                    Rectangle { width: 1; height: parent.height; anchors.right: parent.right; color: "#202024" }

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 0; spacing: 0

                        // Logo area
                        Rectangle {
                            Layout.fillWidth: true; height: 56
                            color: "transparent"

                            Row {
                                anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 18
                                spacing: 10
                                Rectangle {
                                    width: 28; height: 28; radius: 7; color: "#4f46e5"; anchors.verticalCenter: parent.verticalCenter
                                    Image { source: "qrc:/images/cloud.png"; width: 16; height: 16; fillMode: Image.PreserveAspectFit; anchors.centerIn: parent; opacity: 0.9 }
                                }
                                Text { text: "Dotan's Cloud"; color: "#f5f5f7"; font.family: roboto.name; font.pixelSize: 15; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: "#202024" }

                        // Section label
                        Item { Layout.fillWidth: true; height: 36
                            Text { text: "STORAGE"; color: "#444"; font.pixelSize: 10; font.family: roboto.name; font.letterSpacing: 1.2; anchors { left: parent.left; leftMargin: 20; bottom: parent.bottom; bottomMargin: 4 } }
                        }

                        // Nav items
                        component NavItem: Rectangle {
                            property string label: ""
                            property string iconChar: ""
                            property bool isActive: false
                            signal navClicked()

                            Layout.fillWidth: true; height: 36; color: "transparent"
                            radius: 6
                            anchors.leftMargin: 8; anchors.rightMargin: 8

                            Rectangle {
                                anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8; radius: 6
                                color: parent.isActive ? "#1e1e30" : (navMa.containsMouse ? "#1a1a1e" : "transparent")
                                Behavior on color { ColorAnimation { duration: 100 } }

                                // Active indicator bar
                                Rectangle {
                                    visible: parent.parent.isActive
                                    width: 3; height: 18; radius: 2; color: "#4f46e5"
                                    anchors.left: parent.left; anchors.leftMargin: 0; anchors.verticalCenter: parent.verticalCenter
                                }

                                Row {
                                    anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 16
                                    spacing: 10
                                    Text { text: parent.parent.parent.iconChar; color: parent.parent.parent.isActive ? "#818cf8" : "#666"; font.pixelSize: 15; anchors.verticalCenter: parent.verticalCenter }
                                    Text { text: parent.parent.parent.label; color: parent.parent.parent.isActive ? "#e5e7f0" : "#888"; font.pixelSize: 13; font.family: roboto.name; anchors.verticalCenter: parent.verticalCenter }
                                }
                                MouseArea { id: navMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: parent.parent.navClicked() }
                            }
                        }

                        NavItem { id: navAll;      label: "All Files";      iconChar: "⊞"; isActive: contentArea.currentTab === "all";      onNavClicked: { contentArea.currentTab = "all";      Backend.requestCloudFiles() } }
                        NavItem { id: navRecent;   label: "Recent";         iconChar: "⏱"; isActive: contentArea.currentTab === "recent";   onNavClicked: contentArea.currentTab = "recent" }
                        NavItem { id: navFavorites;label: "Favorites";      iconChar: "★"; isActive: contentArea.currentTab === "favorites"; onNavClicked: contentArea.currentTab = "favorites" }
                        NavItem { id: navShared;   label: "Shared with Me"; iconChar: "⇄"; isActive: contentArea.currentTab === "shared";   onNavClicked: { contentArea.currentTab = "shared"; Backend.requestSharedFiles() } }

                        Rectangle { Layout.fillWidth: true; height: 1; color: "#202024"; Layout.topMargin: 12; Layout.bottomMargin: 4 }
                        Item { Layout.fillWidth: true; height: 28
                            Text { text: "TOOLS"; color: "#444"; font.pixelSize: 10; font.family: roboto.name; font.letterSpacing: 1.2; anchors { left: parent.left; leftMargin: 20; bottom: parent.bottom; bottomMargin: 4 } }
                        }

                        NavItem { label: "Create File"; iconChar: "+"; isActive: false; onNavClicked: Backend.ask_connect_to_http() }

                        Item { Layout.fillHeight: true }

                        // Bottom user / logout area
                        Rectangle {
                            Layout.fillWidth: true; height: 54
                            color: "#111113"

                            Rectangle { width: parent.width; height: 1; color: "#202024"; anchors.top: parent.top }

                            Row {
                                anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: 16
                                spacing: 10

                                Rectangle { width: 30; height: 30; radius: 15; color: "#1e1e30"
                                    Text { text: "U"; color: "#818cf8"; font.pixelSize: 13; font.bold: true; anchors.centerIn: parent }
                                }
                            }

                            Rectangle {
                                width: 28; height: 28; radius: 7
                                color: logoutMa.containsMouse ? "#2a1515" : "transparent"
                                anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                Behavior on color { ColorAnimation { duration: 100 } }
                                Text { text: "⏻"; color: logoutMa.containsMouse ? "#f87171" : "#555"; font.pixelSize: 14; anchors.centerIn: parent }
                                MouseArea { id: logoutMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: Backend.exit_app() }
                            }
                        }
                    }
                }

                // ── MAIN CONTENT ─────────────────────────────────────────
                Rectangle {
                    id: contentArea
                    Layout.fillWidth: true; Layout.fillHeight: true
                    color: "#161618"
                    property string currentTab: "all"

                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 32; spacing: 0

                        // ── Top bar ──────────────────────────────────────
                        RowLayout {
                            Layout.fillWidth: true; spacing: 12

                            Column {
                                spacing: 3
                                Text {
                                    text: {
                                        if (contentArea.currentTab === "all")       return "All Files"
                                        if (contentArea.currentTab === "recent")    return "Recent"
                                        if (contentArea.currentTab === "favorites") return "Favorites"
                                        return "Shared with Me"
                                    }
                                    color: "#f5f5f7"; font.family: roboto.name; font.pixelSize: 22; font.bold: true
                                }
                                Text {
                                    text: {
                                        if (contentArea.currentTab === "all")       return cloudModel.count + " file" + (cloudModel.count === 1 ? "" : "s")
                                        if (contentArea.currentTab === "recent")    return recentModel.count + " recent item" + (recentModel.count === 1 ? "" : "s")
                                        if (contentArea.currentTab === "favorites") return favoritesModel.count + " favorite" + (favoritesModel.count === 1 ? "" : "s")
                                        return "Files shared with you"
                                    }
                                    color: "#555"; font.pixelSize: 13; font.family: roboto.name
                                }
                            }

                            Item { Layout.fillWidth: true }

                            // Refresh (only relevant for "all")
                            Rectangle {
                                visible: contentArea.currentTab === "all" || contentArea.currentTab === "shared"
                                width: 36; height: 36; radius: 8
                                color: refBtnMa.containsMouse ? "#1e1e22" : "transparent"
                                border.color: "#2a2a2e"; border.width: 1
                                Behavior on color { ColorAnimation { duration: 100 } }
                                Text { text: "⟳"; color: "#888"; font.pixelSize: 17; anchors.centerIn: parent }
                                MouseArea { id: refBtnMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { if (contentArea.currentTab === "shared") Backend.requestSharedFiles(); else Backend.requestCloudFiles() } }
                            }
                        }

                        Text {
                            visible: actionMessage !== ""
                            text: actionMessage
                            color: actionMessageColor
                            font.pixelSize: 13
                            font.family: roboto.name
                            Layout.topMargin: 8
                            Layout.bottomMargin: 8
                        }

                        // Divider
                        Rectangle { Layout.fillWidth: true; height: 1; color: "#202024"; Layout.topMargin: 20; Layout.bottomMargin: 20 }

                        // ── Column headers (table header) ────────────────
                        RowLayout {
                            Layout.fillWidth: true
                            visible: {
                                if (contentArea.currentTab === "all")       return cloudModel.count > 0
                                if (contentArea.currentTab === "recent")    return recentModel.count > 0
                                if (contentArea.currentTab === "favorites") return favoritesModel.count > 0
                                return false
                            }
                            spacing: 0
                            Layout.bottomMargin: 6

                            Text { text: "Name"; color: "#444"; font.pixelSize: 11; font.family: roboto.name; Layout.fillWidth: true; Layout.leftMargin: 12 }
                            Text { text: contentArea.currentTab === "recent" ? "Opened" : ""; color: "#444"; font.pixelSize: 11; font.family: roboto.name; Layout.preferredWidth: 80 }
                            Text { text: "Actions"; color: "#444"; font.pixelSize: 11; font.family: roboto.name; Layout.preferredWidth: 260 }
                        }

                        // ── File list view ───────────────────────────────
                        // Reusable file row component
                        component FileRow: Rectangle {
                            id: rowRoot
                            property string fileName: ""
                            property string metaText: ""
                            property string ownerName: ""
                            property string accessLevel: "owner"
                            property bool isOwnedFile: ownerName === ""
                            property bool favd: isFavorite(fileName)

                            Layout.fillWidth: true; height: 48; radius: 8
                            color: rowRootMa.containsMouse ? "#1c1c1f" : "transparent"
                            Behavior on color { ColorAnimation { duration: 80 } }

                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 8; spacing: 10

                                // File icon
                                Rectangle {
                                    width: 30; height: 30; radius: 7; color: "#1e1e22"
                                    Layout.alignment: Qt.AlignVCenter
                                    Image { source: "qrc:/images/file.png"; width: 16; height: 16; fillMode: Image.PreserveAspectFit; anchors.centerIn: parent; opacity: 0.7 }
                                }

                                // Name
                                Text {
                                    text: rowRoot.fileName; color: "#d4d4d8"; font.pixelSize: 13; font.family: roboto.name
                                    elide: Text.ElideRight; Layout.fillWidth: true; Layout.alignment: Qt.AlignVCenter
                                }

                                // Meta (e.g. time for recent)
                                Text {
                                    text: rowRoot.metaText; color: "#555"; font.pixelSize: 12; font.family: roboto.name
                                    Layout.preferredWidth: 80; Layout.alignment: Qt.AlignVCenter
                                    visible: rowRoot.metaText !== ""
                                }
                                Text {
                                    text: rowRoot.isOwnedFile ? "" : ("Owner: " + rowRoot.ownerName + " • " + rowRoot.accessLevel)
                                    color: "#666"; font.pixelSize: 11; font.family: roboto.name
                                    Layout.preferredWidth: 160; Layout.alignment: Qt.AlignVCenter
                                    visible: text !== ""
                                }

                                // ── Action buttons (visible on hover) ─────
                                Row {
                                    spacing: 6; Layout.alignment: Qt.AlignVCenter
                                    Layout.preferredWidth: 340
                                    opacity: rowRootMa.containsMouse ? 1 : 0.3
                                    Behavior on opacity { NumberAnimation { duration: 100 } }

                                    // Favorite toggle
                                    Rectangle {
                                        width: 30; height: 30; radius: 7
                                        color: favStarMa.containsMouse ? "#1e1e22" : "transparent"
                                        Behavior on color { ColorAnimation { duration: 80 } }
                                        Text {
                                            text: "★"; font.pixelSize: 15; anchors.centerIn: parent
                                            color: rowRoot.favd ? "#facc15" : "#555"
                                            Behavior on color { ColorAnimation { duration: 100 } }
                                        }
                                        MouseArea { id: favStarMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { toggleFavorite(rowRoot.fileName); rowRoot.favd = isFavorite(rowRoot.fileName) } }
                                    }

                                    // Open
                                    Rectangle {
                                        width: 60; height: 30; radius: 7
                                        color: openActMa.containsPress ? "#111827" : (openActMa.containsMouse ? "#1e293b" : "#172033")
                                        Behavior on color { ColorAnimation { duration: 80 } }
                                        Text { text: "Open"; color: "#60a5fa"; font.pixelSize: 12; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                                        MouseArea { id: openActMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { addToRecent(rowRoot.fileName); Backend.open_file_by_owner(rowRoot.fileName, rowRoot.ownerName) } }
                                    }

                                    // Download
                                    Rectangle {
                                        width: 82; height: 30; radius: 7
                                        color: dlActMa.containsPress ? "#1a1a2e" : (dlActMa.containsMouse ? "#22223a" : "#1a1a2e")
                                        Behavior on color { ColorAnimation { duration: 80 } }
                                        Text { text: "Download"; color: "#a5b4fc"; font.pixelSize: 12; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                                        MouseArea { id: dlActMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { saveDialog.pendingName = rowRoot.fileName; saveDialog.pendingOwner = rowRoot.ownerName; saveDialog.open() } }
                                    }

                                    Rectangle {
                                        visible: rowRoot.isOwnedFile
                                        width: 60; height: 30; radius: 7
                                        color: shareActMa.containsPress ? "#13281c" : (shareActMa.containsMouse ? "#173323" : "#122718")
                                        Behavior on color { ColorAnimation { duration: 80 } }
                                        Text { text: "Share"; color: "#86efac"; font.pixelSize: 12; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                                        MouseArea { id: shareActMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { shareDialog.pendingFileName = rowRoot.fileName; shareDialog.open() } }
                                    }

                                    // Delete (only in "all" tab)
                                    Rectangle {
                                        visible: contentArea.currentTab === "all" && rowRoot.isOwnedFile
                                        width: 64; height: 30; radius: 7
                                        color: delActMa.containsPress ? "#2a0e0e" : (delActMa.containsMouse ? "#3a1010" : "#2a0e0e")
                                        Behavior on color { ColorAnimation { duration: 80 } }
                                        Text { text: "Delete"; color: "#fca5a5"; font.pixelSize: 12; font.bold: true; font.family: roboto.name; anchors.centerIn: parent }
                                        MouseArea { id: delActMa; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { if (isFavorite(rowRoot.fileName)) toggleFavorite(rowRoot.fileName); Backend.delete_file(rowRoot.fileName) } }
                                    }
                                }
                            }
                            MouseArea { id: rowRootMa; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                        }

                        // ── ALL FILES tab ────────────────────────────────
                        ListView {
                            id: allFilesList
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: contentArea.currentTab === "all"
                            model: cloudModel; clip: true; spacing: 2

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                                contentItem: Rectangle { radius: 2; color: "#2e2e38"; implicitWidth: 4 }
                            }

                            delegate: FileRow {
                                fileName: model.name; metaText: ""; ownerName: ""; accessLevel: "owner"; width: allFilesList.width
                                Layout.fillWidth: true
                            }

                            // Empty state
                            Item {
                                anchors.centerIn: parent
                                visible: cloudModel.count === 0; width: parent.width
                                Column { anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                                    Item { width: 1; height: 60 }
                                    Rectangle { width: 56; height: 56; radius: 14; color: "#1e1e22"; anchors.horizontalCenter: parent.horizontalCenter
                                        Image { source: "qrc:/images/cloud.png"; width: 28; height: 28; fillMode: Image.PreserveAspectFit; anchors.centerIn: parent; opacity: 0.35 }
                                    }
                                    Text { text: "No files yet"; color: "#444"; font.pixelSize: 16; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                    Text { text: "Use Create File to get started"; color: "#333"; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                }
                            }
                        }

                        // ── RECENT tab ───────────────────────────────────
                        ListView {
                            id: recentList
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: contentArea.currentTab === "recent"
                            model: recentModel; clip: true; spacing: 2

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                                contentItem: Rectangle { radius: 2; color: "#2e2e38"; implicitWidth: 4 }
                            }

                            delegate: FileRow {
                                fileName: model.name; metaText: model.time; width: recentList.width
                                Layout.fillWidth: true
                            }

                            Item {
                                anchors.centerIn: parent
                                visible: recentModel.count === 0; width: parent.width
                                Column { anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                                    Item { width: 1; height: 60 }
                                    Text { text: "⏱"; color: "#333"; font.pixelSize: 36; anchors.horizontalCenter: parent.horizontalCenter }
                                    Text { text: "No recent files"; color: "#444"; font.pixelSize: 16; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                    Text { text: "Files you open or download will appear here"; color: "#333"; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                }
                            }
                        }

                        // ── FAVORITES tab ────────────────────────────────
                        ListView {
                            id: favoritesList
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: contentArea.currentTab === "favorites"
                            model: favoritesModel; clip: true; spacing: 2

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                                contentItem: Rectangle { radius: 2; color: "#2e2e38"; implicitWidth: 4 }
                            }

                            delegate: FileRow {
                                fileName: model.name; metaText: ""; width: favoritesList.width
                                Layout.fillWidth: true
                            }

                            Item {
                                anchors.centerIn: parent
                                visible: favoritesModel.count === 0; width: parent.width
                                Column { anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                                    Item { width: 1; height: 60 }
                                    Text { text: "★"; color: "#333"; font.pixelSize: 36; anchors.horizontalCenter: parent.horizontalCenter }
                                    Text { text: "No favorites yet"; color: "#444"; font.pixelSize: 16; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                    Text { text: "Star files to find them quickly"; color: "#333"; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                }
                            }
                        }

                        // ── SHARED WITH ME tab ───────────────────────────
                        ListView {
                            id: sharedFilesList
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: contentArea.currentTab === "shared"
                            model: sharedModel; clip: true; spacing: 2

                            ScrollBar.vertical: ScrollBar {
                                policy: ScrollBar.AsNeeded
                                contentItem: Rectangle { radius: 2; color: "#2e2e38"; implicitWidth: 4 }
                            }

                            delegate: FileRow {
                                fileName: model.name
                                ownerName: model.owner
                                accessLevel: model.access
                                metaText: ""
                                width: sharedFilesList.width
                                Layout.fillWidth: true
                            }

                            Item {
                                anchors.centerIn: parent
                                visible: sharedModel.count === 0; width: parent.width
                                Column {
                                    anchors.centerIn: parent; spacing: 10
                                    Text { text: "⇄"; color: "#333"; font.pixelSize: 36; anchors.horizontalCenter: parent.horizontalCenter }
                                    Text { text: "No shared files yet"; color: "#444"; font.pixelSize: 16; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                    Text { text: "Files others share with you will appear here"; color: "#333"; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                }
                            }
                        }
                        Item {
                            Layout.fillWidth: true; Layout.fillHeight: true
                            visible: false

                            Column {
                                anchors.centerIn: parent; spacing: 10
                                Text { text: "⇄"; color: "#333"; font.pixelSize: 36; anchors.horizontalCenter: parent.horizontalCenter }
                                Text { text: "Shared files coming soon"; color: "#444"; font.pixelSize: 16; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                                Text { text: "Files others share with you will appear here"; color: "#333"; font.pixelSize: 13; anchors.horizontalCenter: parent.horizontalCenter; font.family: roboto.name }
                            }
                        }
                    }
                }
            }
        }
    }
}
