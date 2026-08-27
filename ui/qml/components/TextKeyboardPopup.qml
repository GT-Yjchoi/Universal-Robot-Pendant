import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: popup

    property string title: "텍스트 입력"
    property bool password: false
    property bool shifted: false
    property bool korean: true
    property bool replaceOnNextInput: false
    property alias inputText: editor.text

    readonly property var initials: [
        "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
        "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"
    ]
    readonly property var vowels: [
        "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
        "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"
    ]
    readonly property var finals: [
        "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
        "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
        "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"
    ]
    readonly property var englishRows: [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l", "-"],
        ["z", "x", "c", "v", "b", "n", "m", "_", ".", "⌫"]
    ]
    readonly property var koreanRows: [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["ㅂ", "ㅈ", "ㄷ", "ㄱ", "ㅅ", "ㅛ", "ㅕ", "ㅑ", "ㅐ", "ㅔ"],
        ["ㅁ", "ㄴ", "ㅇ", "ㄹ", "ㅎ", "ㅗ", "ㅓ", "ㅏ", "ㅣ", "-"],
        ["ㅋ", "ㅌ", "ㅊ", "ㅍ", "ㅠ", "ㅜ", "ㅡ", "_", ".", "⌫"]
    ]

    signal accepted(string value)
    signal rejected()

    function openText(value) {
        editor.text = value
        replaceOnNextInput = !password && editor.text.length > 0
        shifted = false
        korean = true
        open()
        editor.forceActiveFocus()
    }

    function shiftedKorean(key) {
        var pairs = {
            "ㅂ": "ㅃ", "ㅈ": "ㅉ", "ㄷ": "ㄸ", "ㄱ": "ㄲ",
            "ㅅ": "ㅆ", "ㅐ": "ㅒ", "ㅔ": "ㅖ"
        }
        return pairs[key] || key
    }

    function keyLabel(key) {
        if (key === "⌫")
            return key
        if (korean)
            return shifted ? shiftedKorean(key) : key
        return shifted && key.length === 1 ? key.toUpperCase() : key
    }

    function compoundVowel(first, second) {
        var pairs = {
            "ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ",
            "ㅜㅓ": "ㅝ", "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ",
            "ㅡㅣ": "ㅢ"
        }
        return pairs[first + second] || ""
    }

    function compoundFinal(first, second) {
        var pairs = {
            "ㄱㅅ": "ㄳ", "ㄴㅈ": "ㄵ", "ㄴㅎ": "ㄶ",
            "ㄹㄱ": "ㄺ", "ㄹㅁ": "ㄻ", "ㄹㅂ": "ㄼ", "ㄹㅅ": "ㄽ",
            "ㄹㅌ": "ㄾ", "ㄹㅍ": "ㄿ", "ㄹㅎ": "ㅀ", "ㅂㅅ": "ㅄ"
        }
        return pairs[first + second] || ""
    }

    function splitFinal(value) {
        var pairs = {
            "ㄳ": ["ㄱ", "ㅅ"], "ㄵ": ["ㄴ", "ㅈ"], "ㄶ": ["ㄴ", "ㅎ"],
            "ㄺ": ["ㄹ", "ㄱ"], "ㄻ": ["ㄹ", "ㅁ"], "ㄼ": ["ㄹ", "ㅂ"],
            "ㄽ": ["ㄹ", "ㅅ"], "ㄾ": ["ㄹ", "ㅌ"], "ㄿ": ["ㄹ", "ㅍ"],
            "ㅀ": ["ㄹ", "ㅎ"], "ㅄ": ["ㅂ", "ㅅ"]
        }
        return pairs[value] || null
    }

    function simpleVowel(value) {
        var first = {
            "ㅘ": "ㅗ", "ㅙ": "ㅗ", "ㅚ": "ㅗ",
            "ㅝ": "ㅜ", "ㅞ": "ㅜ", "ㅟ": "ㅜ", "ㅢ": "ㅡ"
        }
        return first[value] || ""
    }

    function syllableParts(character) {
        if (!character || character.length === 0)
            return null
        var code = character.charCodeAt(0)
        if (code < 0xAC00 || code > 0xD7A3)
            return null
        var offset = code - 0xAC00
        return {
            initial: Math.floor(offset / 588),
            vowel: Math.floor((offset % 588) / 28),
            final: offset % 28
        }
    }

    function makeSyllable(initialIndex, vowelIndex, finalIndex) {
        return String.fromCharCode(0xAC00 + ((initialIndex * 21 + vowelIndex) * 28) + finalIndex)
    }

    function appendKorean(key) {
        var value = editor.text
        if (value.length === 0) {
            editor.text = key
            return
        }

        var prefix = value.slice(0, -1)
        var last = value.slice(-1)
        var parts = syllableParts(last)
        var consonantIndex = initials.indexOf(key)
        var vowelIndex = vowels.indexOf(key)

        if (vowelIndex >= 0) {
            if (parts !== null) {
                if (parts.final === 0) {
                    var joinedVowel = compoundVowel(vowels[parts.vowel], key)
                    if (joinedVowel !== "") {
                        editor.text = prefix + makeSyllable(
                            parts.initial, vowels.indexOf(joinedVowel), 0
                        )
                    } else {
                        editor.text += key
                    }
                    return
                }

                var oldFinal = finals[parts.final]
                var divided = splitFinal(oldFinal)
                var remainingFinal = divided === null ? "" : divided[0]
                var movingInitial = divided === null ? oldFinal : divided[1]
                var movingIndex = initials.indexOf(movingInitial)
                if (movingIndex >= 0) {
                    editor.text = prefix
                        + makeSyllable(parts.initial, parts.vowel, finals.indexOf(remainingFinal))
                        + makeSyllable(movingIndex, vowelIndex, 0)
                } else {
                    editor.text += key
                }
                return
            }

            var priorInitial = initials.indexOf(last)
            if (priorInitial >= 0) {
                editor.text = prefix + makeSyllable(priorInitial, vowelIndex, 0)
                return
            }

            var joinedStandalone = compoundVowel(last, key)
            editor.text = joinedStandalone !== "" ? prefix + joinedStandalone : value + key
            return
        }

        if (consonantIndex >= 0 && parts !== null) {
            if (parts.final === 0) {
                var newFinalIndex = finals.indexOf(key)
                editor.text = newFinalIndex > 0
                    ? prefix + makeSyllable(parts.initial, parts.vowel, newFinalIndex)
                    : value + key
                return
            }
            var joinedFinal = compoundFinal(finals[parts.final], key)
            if (joinedFinal !== "") {
                editor.text = prefix + makeSyllable(
                    parts.initial, parts.vowel, finals.indexOf(joinedFinal)
                )
                return
            }
        }
        editor.text += key
    }

    function backspace() {
        var value = editor.text
        if (value.length === 0)
            return
        var prefix = value.slice(0, -1)
        var last = value.slice(-1)
        var parts = syllableParts(last)
        if (parts === null) {
            editor.text = prefix
            return
        }
        if (parts.final > 0) {
            var divided = splitFinal(finals[parts.final])
            var finalIndex = divided === null ? 0 : finals.indexOf(divided[0])
            editor.text = prefix + makeSyllable(parts.initial, parts.vowel, finalIndex)
            return
        }
        var reducedVowel = simpleVowel(vowels[parts.vowel])
        editor.text = reducedVowel !== ""
            ? prefix + makeSyllable(parts.initial, vowels.indexOf(reducedVowel), 0)
            : prefix + initials[parts.initial]
    }

    function pressKey(rawKey) {
        if (rawKey === "⌫") {
            replaceOnNextInput = false
            backspace()
            return
        }
        if (replaceOnNextInput) {
            editor.text = ""
            replaceOnNextInput = false
        }
        var key = keyLabel(rawKey)
        if (korean && (initials.indexOf(key) >= 0 || vowels.indexOf(key) >= 0))
            appendKorean(key)
        else
            editor.text += key
    }

    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: 920
    height: 560
    padding: 16

    Overlay.modal: Rectangle { color: "#a0000000" }
    background: Rectangle {
        color: "#17212C"
        radius: 14
        border.color: "#468CFF"
        border.width: 2
    }

    contentItem: ColumnLayout {
        spacing: 8

        Text {
            Layout.fillWidth: true
            text: popup.title
            color: "#DCE9F7"
            font.pixelSize: 22
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
        }

        TextField {
            id: editor
            Layout.fillWidth: true
            Layout.preferredHeight: 66
            leftPadding: 16
            rightPadding: 16
            color: "#FFFFFF"
            selectionColor: "#468CFF"
            selectedTextColor: "#FFFFFF"
            font.pixelSize: 28
            echoMode: popup.password ? TextInput.Password : TextInput.Normal
            onTextEdited: popup.replaceOnNextInput = false
            background: Rectangle {
                color: "#0D1925"
                radius: 8
                border.color: editor.activeFocus ? "#6EA6FF" : "#35506A"
                border.width: editor.activeFocus ? 2 : 1
            }
            cursorDelegate: Rectangle { width: 2; color: "#FFFFFF" }
        }

        Repeater {
            model: popup.korean ? popup.koreanRows : popup.englishRows
            RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: parent.modelData
                    PendantButton {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 58
                        text: popup.keyLabel(modelData)
                        font.pixelSize: popup.korean ? 21 : 19
                        onClicked: popup.pressKey(modelData)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 7
            PendantButton {
                Layout.preferredWidth: 115
                Layout.preferredHeight: 58
                text: "한/영"
                accent: popup.korean ? "#468CFF" : "#6F88A2"
                onClicked: {
                    popup.korean = !popup.korean
                    popup.shifted = false
                }
            }
            PendantButton {
                Layout.preferredWidth: 120
                Layout.preferredHeight: 58
                text: popup.korean ? "쌍자음" : (popup.shifted ? "ABC" : "abc")
                accent: popup.shifted ? "#8E6FD1" : "#6F88A2"
                onClicked: popup.shifted = !popup.shifted
            }
            PendantButton {
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                text: "SPACE"
                onClicked: {
                    if (popup.replaceOnNextInput) {
                        editor.text = ""
                        popup.replaceOnNextInput = false
                    }
                    editor.text += " "
                }
            }
            PendantButton {
                Layout.preferredWidth: 145
                Layout.preferredHeight: 58
                text: "취소"
                accent: "#A75050"
                onClicked: {
                    popup.close()
                    popup.rejected()
                }
            }
            PendantButton {
                Layout.preferredWidth: 145
                Layout.preferredHeight: 58
                text: "적용"
                accent: "#468CFF"
                onClicked: {
                    var out = editor.text
                    popup.close()
                    popup.accepted(out)
                }
            }
        }
    }
}
