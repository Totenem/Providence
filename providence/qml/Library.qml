import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: shell
    property var snapshot: library ? library.state : ({})
    property bool dark: snapshot.dark
    property color ink: dark ? '#e8eef6' : '#233044'
    property color muted: dark ? '#a7b5c7' : '#637184'
    property color panel: dark ? '#1a2533' : '#ffffff'
    property color line: dark ? '#344355' : '#e1e7ee'
    property color accent: dark ? '#73dfb4' : '#147d59'
    property color buttonFill: dark ? '#293b50' : '#e1eaf4'
    property color buttonHover: dark ? '#3a526b' : '#ceddeb'
    property int motion: snapshot.reducedMotion ? 0 : 160
    property int offeredSession: -1
    color: dark ? '#111923' : '#f4f7fa'
    Behavior on color { ColorAnimation { duration: shell.motion } }

    component Caption: Label {
        color: shell.ink
        font.family: 'Segoe UI'
        font.pixelSize: 13
        elide: Text.ElideRight
    }
    component Action: Button {
        id: control
        property bool primary: false
        hoverEnabled: true
        Accessible.name: text
        contentItem: Caption { text: control.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: !control.enabled ? shell.muted : control.primary ? (shell.dark ? '#10251c' : '#ffffff') : shell.ink }
        background: Rectangle {
            radius: 9
            color: control.primary ? (control.hovered ? (shell.dark ? '#9cebc9' : '#116544') : shell.accent) : control.down ? (shell.dark ? '#203248' : '#bdcfdf') : control.hovered ? shell.buttonHover : shell.buttonFill
            border.color: control.activeFocus ? shell.accent : (shell.dark ? '#4b6077' : '#bdcede')
            Behavior on color { ColorAnimation { duration: shell.motion } }
        }
        implicitHeight: 38
        leftPadding: 14
        rightPadding: 14
    }
    component Choice: ComboBox {
        id: choice
        property string field
        objectName: 'filter-' + field
        model: shell.snapshot.filters[field].items
        currentIndex: shell.snapshot.filters[field].index
        onActivated: library.filter(field, currentIndex)
        implicitHeight: 36
        implicitWidth: 120
        font.family: 'Segoe UI'
        font.pixelSize: 12
        contentItem: Caption { text: choice.displayText; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 28 }
        indicator: Caption { x: choice.width - 22; y: (choice.height - height) / 2; text: '⌄'; color: shell.muted }
        background: Rectangle { color: choice.hovered ? shell.buttonHover : shell.buttonFill; radius: 8; border.color: choice.activeFocus ? shell.accent : shell.line }
        popup: Popup {
            id: choices
            objectName: 'popup-' + choice.field
            y: choice.height + 6
            width: Math.max(choice.width, 220)
            padding: 8
            implicitHeight: Math.min(310, shell.height - 80, choiceList.contentHeight + 66)
            property var filtered: choice.model.map((text, index) => ({label: text, original: index})).filter(item => item.label.toLowerCase().includes(filterSearch.text.toLowerCase()))
            background: Rectangle { color: shell.panel; radius: 10; border.color: shell.line; border.width: 1 }
            onOpened: { filterSearch.clear(); filterSearch.forceActiveFocus() }
            contentItem: ColumnLayout {
                spacing: 8
                TextField {
                    id: filterSearch
                    Layout.fillWidth: true
                    Layout.preferredHeight: 34
                    placeholderText: 'Find an option…'
                    color: shell.ink
                    placeholderTextColor: shell.muted
                    selectByMouse: true
                    background: Rectangle { color: shell.buttonFill; radius: 6; border.color: shell.line }
                    onAccepted: { if (choices.filtered.length) { library.filter(choice.field, choices.filtered[0].original); choices.close() } }
                    Keys.onDownPressed: { choiceList.forceActiveFocus(); choiceList.currentIndex = 0 }
                }
                ListView {
                    id: choiceList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: choices.filtered
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: SlimScroll {}
                    delegate: ItemDelegate {
                        required property var modelData
                        required property int index
                        width: choiceList.width - 12
                        height: 34
                        contentItem: Caption { text: modelData.label; verticalAlignment: Text.AlignVCenter }
                        background: Rectangle { radius: 6; color: hovered || ListView.isCurrentItem ? shell.buttonHover : modelData.original === choice.currentIndex ? (shell.dark ? '#244c40' : '#dbeee6') : 'transparent' }
                        onClicked: { library.filter(choice.field, modelData.original); choices.close() }
                    }
                    Keys.onReturnPressed: { if (currentIndex >= 0) { library.filter(choice.field, choices.filtered[currentIndex].original); choices.close() } }
                }
            }
        }
        Accessible.name: field + ' filter'
    }
    component SlimScroll: ScrollBar {
        id: bar
        width: 8
        policy: ScrollBar.AsNeeded
        visible: size < 1
        contentItem: Rectangle { implicitWidth: 6; radius: 3; color: bar.pressed ? shell.accent : shell.dark ? '#61758b' : '#a1b2c3'; opacity: bar.active ? 1 : 0.65 }
        background: Rectangle { color: 'transparent' }
    }
    component ClueChoice: ComboBox {
        id: clue
        property var options: []
        property var selectedValue: options[currentIndex] ? options[currentIndex].value : ''
        model: options.map(option => option.label)
        implicitHeight: 36
        Layout.fillWidth: true
        contentItem: Caption { text: clue.displayText; verticalAlignment: Text.AlignVCenter; leftPadding: 10; rightPadding: 28 }
        indicator: Caption { x: clue.width - 22; y: (clue.height - height) / 2; text: '⌄'; color: shell.muted }
        background: Rectangle { color: clue.hovered ? shell.buttonHover : shell.buttonFill; radius: 8; border.color: shell.line }
        popup: Popup {
            y: clue.height + 4
            width: clue.width
            padding: 6
            implicitHeight: Math.min(210, optionsList.contentHeight + 12)
            background: Rectangle { color: shell.panel; radius: 8; border.color: shell.line }
            contentItem: ListView {
                id: optionsList
                model: clue.options
                clip: true
                ScrollBar.vertical: SlimScroll {}
                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: optionsList.width - 12
                    height: 36
                    contentItem: Caption { text: modelData.label; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { radius: 6; color: hovered ? shell.buttonHover : 'transparent' }
                    onClicked: { clue.currentIndex = index; clue.popup.close() }
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 238
            Layout.fillHeight: true
            color: shell.panel
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: shell.line }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 12
                RowLayout {
                    Layout.topMargin: 10
                    spacing: 10
                    Image { source: '../assets/providence.png'; Layout.preferredWidth: 34; Layout.preferredHeight: 34; fillMode: Image.PreserveAspectFit; smooth: true }
                    Caption { text: 'Providence'; font.pixelSize: 23; font.weight: Font.DemiBold }
                }
                Caption { text: 'Your files, within reach'; color: shell.muted; Layout.bottomMargin: 24 }
                Action { text: '▦  Library'; Layout.fillWidth: true; enabled: shell.snapshot.onboarded; primary: true; onClicked: library.browse('') }
                Action { text: '⚙  Locations & settings'; Layout.fillWidth: true; onClicked: library.panel(2) }
                Action { text: '◉  Index health'; Layout.fillWidth: true; onClicked: library.panel(3) }
                Action { text: '▧  Image search'; Layout.fillWidth: true; enabled: shell.snapshot.onboarded; onClicked: library.tools('images') }
                Action { text: '▱  Duplicate review'; Layout.fillWidth: true; enabled: shell.snapshot.onboarded; onClicked: library.tools('duplicates') }
                Caption { text: 'LOCATIONS'; color: shell.muted; font.pixelSize: 11; font.letterSpacing: 1.5; Layout.topMargin: 22 }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: shell.snapshot.roots
                    spacing: 6
                    delegate: Action {
                        required property string modelData
                        width: Math.max(0, ListView.view.width - 12)
                        text: '▱  ' + modelData
                        ToolTip.visible: hovered
                        ToolTip.text: modelData
                        onClicked: library.browse(modelData)
                    }
                    ScrollBar.vertical: SlimScroll {}
                }
                Caption { text: shell.snapshot.count; color: shell.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 22
            spacing: 14
            RowLayout {
                Layout.fillWidth: true
                Caption { text: shell.snapshot.onboarded ? 'Your library' : 'Welcome to Providence'; font.pixelSize: 27; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Action { text: shell.snapshot.pause; visible: shell.snapshot.onboarded; onClicked: library.action('pause') }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: shell.snapshot.busy ? 64 : 0
                visible: height > 0
                clip: true
                radius: 12
                color: shell.panel
                border.color: shell.line
                Behavior on Layout.preferredHeight { NumberAnimation { duration: shell.motion; easing.type: Easing.OutCubic } }
                RowLayout {
                    Layout.fillWidth: true
                    anchors.fill: parent
                    anchors.margins: 12
                    BusyIndicator { running: shell.snapshot.busy && !shell.snapshot.reducedMotion; Layout.preferredWidth: 32; Layout.preferredHeight: 32 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Caption { text: shell.snapshot.phase; color: shell.accent }
                        Caption { text: shell.snapshot.progress; color: shell.muted; Layout.fillWidth: true }
                    }
                }
            }
            ColumnLayout {
                visible: !shell.snapshot.onboarded
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18
                Caption { text: 'Choose where Providence can look'; font.pixelSize: 21 }
                Caption { text: 'Discover filenames first, then make document text and scans searchable.\nNew and changed files update automatically while Providence is open.'; color: shell.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                RowLayout {
                    Action { text: 'Choose folder'; primary: true; onClicked: library.action('choose') }
                    Action { text: 'Use local drives'; onClicked: library.action('drives') }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: shell.snapshot.pending
                    spacing: 8
                    delegate: RowLayout {
                        required property string modelData
                        required property int index
                        width: ListView.view.width
                        Caption { text: modelData; Layout.fillWidth: true }
                        Action { text: 'Remove'; onClicked: library.removePending(index) }
                    }
                }
                Caption { text: shell.snapshot.feedback; color: shell.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Action { text: 'Start my library →'; primary: true; enabled: shell.snapshot.pending.length > 0; onClicked: library.action('start') }
            }
            ColumnLayout {
                visible: shell.snapshot.onboarded
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 12
                RowLayout {
                    Action { text: '←'; enabled: shell.snapshot.back; Accessible.name: 'Back'; onClicked: library.action('back') }
                    Action { text: '→'; enabled: shell.snapshot.forward; Accessible.name: 'Forward'; onClicked: library.action('forward') }
                    Action { text: '↑'; enabled: shell.snapshot.up; Accessible.name: 'Parent folder'; onClicked: library.action('up') }
                    TextField {
                        id: query
                        Layout.fillWidth: true
                        implicitHeight: 42
                        color: shell.ink
                        placeholderTextColor: shell.muted
                        placeholderText: 'Filename, exact words, or what you remember…'
                        text: shell.snapshot.query
                        selectByMouse: true
                        Accessible.name: 'Search library'
                        font.family: 'Segoe UI'
                        background: Rectangle { color: shell.panel; radius: 10; border.color: query.activeFocus ? shell.accent : shell.line; Behavior on border.color { ColorAnimation { duration: shell.motion } } }
                        onTextEdited: library.search(text)
                        onAccepted: library.submitSearch(text)
                    }
                    Action { text: '×'; Accessible.name: 'Clear search'; onClicked: library.search('') }
                    Action { text: 'Search'; primary: true; onClicked: library.submitSearch(query.text) }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 5
                    Repeater {
                        model: shell.snapshot.crumbs
                        delegate: Action { required property var modelData; text: modelData.name + ' ›'; onClicked: library.browse(modelData.path) }
                    }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: shell.line }
                Caption { text: 'FILTER & SORT'; font.pixelSize: 10; font.letterSpacing: 1.2; color: shell.muted }
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Choice { field: 'type' }
                    Choice { field: 'status' }
                    Choice { field: 'date' }
                    Choice { field: 'size' }
                    Choice { field: 'sort' }
                    Action { text: 'Reset'; onClicked: library.action('clear') }
                }
                Caption { text: 'FOLDERS'; visible: shell.snapshot.folders.length > 0; font.pixelSize: 10; font.letterSpacing: 1.2; color: shell.muted }
                Flickable {
                    Layout.fillWidth: true
                    Layout.preferredHeight: shell.snapshot.folders.length ? 40 : 0
                    contentWidth: folderRow.width
                    clip: true
                    Row {
                        id: folderRow
                        spacing: 6
                        Repeater {
                            model: shell.snapshot.folders
                            delegate: Action { required property var modelData; text: '▱  ' + modelData.name; onClicked: library.browse(modelData.path) }
                        }
                    }
                }
                Caption { text: 'FILES  ·  ' + shell.snapshot.summary; color: shell.muted; font.weight: Font.DemiBold }
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: shell.panel
                    radius: 12
                    border.color: shell.line
                    Rectangle {
                        id: searchProgress
                        objectName: 'search-progress'
                        visible: shell.snapshot.search.running || shell.snapshot.search.percent === 100
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 12
                        height: slowNotice.visible ? 190 : 110
                        radius: 10
                        color: shell.dark ? '#203344' : '#eef5fa'
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            RowLayout {
                                BusyIndicator { running: shell.snapshot.search.running && !shell.snapshot.reducedMotion; visible: shell.snapshot.search.running; palette.dark: shell.accent; Layout.preferredWidth: 26; Layout.preferredHeight: 26 }
                                Caption { text: shell.snapshot.search.phase; Layout.fillWidth: true; font.weight: Font.DemiBold }
                                Caption { text: shell.snapshot.search.percent + '%'; color: shell.accent; font.weight: Font.Bold }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                radius: 3
                                color: shell.line
                                Rectangle { width: parent.width * shell.snapshot.search.percent / 100; height: parent.height; radius: 3; color: shell.accent; Behavior on width { NumberAnimation { duration: shell.motion } } }
                            }
                            Caption { text: shell.snapshot.search.running ? shell.snapshot.search.helper : 'Your results are ready.'; color: shell.muted; Layout.fillWidth: true }
                            RowLayout {
                                Caption { text: 'Search stages · ' + shell.snapshot.search.elapsed + 's'; color: shell.muted; font.pixelSize: 10; Layout.fillWidth: true }
                            }
                            RowLayout {
                                id: slowNotice
                                visible: shell.snapshot.search.slow
                                Layout.fillWidth: true
                                Caption { text: 'Taking a little longer. A few clues may help narrow the search.'; Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.Wrap }
                                Action { text: 'Add clues'; primary: true; onClicked: cluesPopup.open() }
                            }
                        }
                    }
                    ListView {
                        id: files
                        anchors.fill: parent
                        anchors.margins: 8
                        anchors.topMargin: searchProgress.visible ? searchProgress.height + 24 : 8
                        clip: true
                        model: library ? library.rows : []
                        spacing: 4
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: SlimScroll {}
                        delegate: Rectangle {
                            id: entry
                            objectName: 'file-row-' + index
                            required property var modelData
                            required property int index
                            width: Math.max(0, files.width - 14)
                            height: 66
                            radius: 8
                            color: shell.snapshot.selected === modelData.path ? (shell.dark ? '#244c40' : '#dbeee6') : mouse.containsMouse ? (shell.dark ? '#2b3b4d' : '#edf2f7') : 'transparent'
                            Behavior on color { ColorAnimation { duration: shell.motion } }
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                Rectangle {
                                    Layout.preferredWidth: 34; Layout.minimumWidth: 34; Layout.maximumWidth: 34; height: 38; radius: 5; color: shell.dark ? '#354a5a' : '#e7eef5'
                                    Caption { anchors.centerIn: parent; text: entry.modelData.kind || 'FILE'; font.pixelSize: 9; font.weight: Font.Bold }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 0
                                    Layout.preferredWidth: 100
                                    spacing: 3
                                    Caption { text: entry.modelData.name; font.weight: Font.DemiBold; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1 }
                                    Caption { text: entry.modelData.path; color: shell.muted; font.pixelSize: 11; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1 }
                                }
                                ColumnLayout {
                                    Layout.preferredWidth: 100
                                    Layout.minimumWidth: 100
                                    Layout.maximumWidth: 100
                                    Caption { text: entry.modelData.status; color: shell.accent; font.pixelSize: 11; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignRight }
                                    Caption { text: entry.modelData.match || entry.modelData.size; color: shell.muted; font.pixelSize: 11; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; horizontalAlignment: Text.AlignRight }
                                }
                            }
                            MouseArea {
                                id: mouse
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: function(event) { library.select(entry.index); files.forceActiveFocus(); if (event.button === Qt.RightButton) context.popup() }
                                onDoubleClicked: library.action('open')
                            }
                            Accessible.role: Accessible.ListItem
                            Accessible.name: modelData.name + ', ' + modelData.status
                            Accessible.onPressAction: library.select(index)
                        }
                        Keys.onPressed: function(event) {
                            let index = library.rows.findIndex(row => row.path === shell.snapshot.selected)
                            if (event.key === Qt.Key_Down) { library.select(Math.min(index + 1, count - 1)); positionViewAtIndex(index + 1, ListView.Contain); event.accepted = true }
                            if (event.key === Qt.Key_Up) { library.select(Math.max(index - 1, 0)); positionViewAtIndex(index - 1, ListView.Contain); event.accepted = true }
                            if (event.key === Qt.Key_Return) { library.action('open'); event.accepted = true }
                        }
                    }
                    Caption { anchors.centerIn: parent; visible: files.count === 0; text: 'Files appear here as they are discovered.'; color: shell.muted }
                }
                RowLayout {
                    Action { text: 'Previous'; enabled: shell.snapshot.previous; onClicked: library.action('previous') }
                    Caption { text: shell.snapshot.paging; color: shell.muted; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                    Action { text: 'Next'; enabled: shell.snapshot.next; onClicked: library.action('next') }
                }
            }
            Caption { text: shell.snapshot.status; color: shell.muted; Layout.fillWidth: true; ToolTip.visible: statusHover.hovered; ToolTip.text: text; HoverHandler { id: statusHover } }
        }
    }
    Menu {
        id: context
        palette.window: shell.panel
        palette.base: shell.panel
        palette.text: shell.ink
        palette.buttonText: shell.ink
        palette.highlight: shell.buttonHover
        palette.highlightedText: shell.ink
        background: Rectangle { color: shell.panel; radius: 8; border.color: shell.line }
        MenuItem { text: 'Open file'; onTriggered: library.action('open') }
        MenuItem { text: 'Show in Explorer'; onTriggered: library.action('reveal') }
        MenuItem { text: 'Copy path'; onTriggered: library.action('copy') }
        MenuItem { text: 'Copy passage'; onTriggered: library.action('passage') }
        MenuItem { text: 'Retry indexing'; onTriggered: library.action('retry') }
    }
    Popup {
        id: cluesPopup
        objectName: 'search-clues'
        x: (shell.width - width) / 2
        y: (shell.height - height) / 2
        width: Math.min(520, shell.width - 40)
        implicitHeight: Math.min(500, shell.height - 40)
        padding: 22
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: shell.panel; radius: 14; border.color: shell.line }
        onOpened: { folderClue.currentIndex = 0; countClue.currentIndex = 0; typeClue.currentIndex = 0; dateClue.currentIndex = 0 }
        contentItem: ColumnLayout {
            spacing: 8
            Caption { text: 'A little more to go on'; font.pixelSize: 22; font.weight: Font.DemiBold }
            Caption { text: 'This search has taken over 20 seconds. Share anything you remember; unknown details are fine.'; color: shell.muted; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Caption { text: 'What folder might it have been in?' }
            ClueChoice { id: folderClue; options: shell.snapshot.clueFolders }
            Caption { text: 'How many connected files are you looking for?' }
            ClueChoice { id: countClue; options: [{label:'I have no clue',value:0},{label:'One file',value:1},{label:'About 5 files',value:5},{label:'About 10 files',value:10},{label:'About 20 files',value:20},{label:'About 50 files',value:50}] }
            Caption { text: 'What kind of file do you remember?' }
            ClueChoice { id: typeClue; options: [{label:'I have no clue',value:''},{label:'PDF',value:'.pdf'},{label:'Word document',value:'.docx'},{label:'Text file',value:'.txt'},{label:'Markdown',value:'.md'},{label:'PNG image',value:'.png'},{label:'JPEG image',value:'.jpg'}] }
            Caption { text: 'Roughly when was it last changed?' }
            ClueChoice { id: dateClue; options: [{label:'I have no clue',value:0},{label:'In the last week',value:7},{label:'In the last month',value:30},{label:'In the last year',value:365}] }
            RowLayout {
                Layout.topMargin: 8
                Layout.fillWidth: true
                Action { text: 'Keep searching'; onClicked: cluesPopup.close() }
                Item { Layout.fillWidth: true }
                Action { text: 'Search with these clues'; primary: true; onClicked: { library.refineSearch({folder:folderClue.selectedValue, count:countClue.selectedValue, suffix:typeClue.selectedValue, days:dateClue.selectedValue}); cluesPopup.close() } }
            }
        }
    }
    Connections {
        target: library
        function onChanged() {
            if (shell.snapshot.search.slow && shell.offeredSession !== shell.snapshot.search.session) {
                shell.offeredSession = shell.snapshot.search.session
                cluesPopup.open()
            } else if (!shell.snapshot.search.running) {
                cluesPopup.close()
            }
        }
    }
    Shortcut { sequence: 'Ctrl+L'; onActivated: { query.forceActiveFocus(); query.selectAll() } }
    Shortcut { sequence: 'Escape'; onActivated: library.search('') }
}
