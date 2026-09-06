import QtQuick
import QtTest
import ".." as Pulse

TestCase {
    name: "CpuPulseWidgets"
    when: windowShown
    // The die only paints while it is actually on screen, so the case itself
    // has to be shown or nothing under test ever repaints.
    visible: true
    width: 740; height: 240

    Pulse.HistoryGraph { id: graph; width: 700; height: 139 }
    Pulse.CpuChip { id: chip; width: 28; height: 25; compact: true; animate: false }

    function test_empty_and_replaced_history() {
        failOnWarning(/.*/)
        graph.historyData = {points: [[100, 40, 60, null, 0, 1, 'boot']], seconds: 3600, now: 100, bucket: 15}
        graph.hoverIndex = 0
        compare(graph.hoverPoint[1], 40)
        graph.historyData = {points: [], seconds: 3600, now: 101, bucket: 15}
        compare(graph.hoverPoint, null)
        graph.hoverIndex = 0
        compare(graph.hoverPoint, null)
        wait(30)
    }

    function test_disabling_animation_paints_final_load() {
        chip.animate = true
        chip.cores = [100]
        wait(50)
        chip.shown = [0]
        chip.animate = false
        tryCompare(chip, 'shown', [1])
    }
}
