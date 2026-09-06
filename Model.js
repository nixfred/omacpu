.pragma library
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v) || 0)) }
// Colour follows headroom: dark red with none, yellow at half, green when idle.
function ramp(percent) {
    var f = clamp(percent, 0, 100) / 100
    var a = f <= 0.5 ? [133, 13, 41] : [239, 204, 69]
    var b = f <= 0.5 ? [239, 204, 69] : [67, 242, 161]
    var t = f <= 0.5 ? f * 2 : (f - 0.5) * 2
    return Qt.rgba((a[0]+(b[0]-a[0])*t)/255, (a[1]+(b[1]-a[1])*t)/255, (a[2]+(b[2]-a[2])*t)/255, 1)
}
function pct(v) { return (Number(v)||0).toFixed(1)+'%' }
function ghz(khz) { return khz === null || khz === undefined || isNaN(Number(khz)) ? '—' : ((Number(khz)||0)/1000000).toFixed(2)+' GHz' }
function temp(v) { return v === null || v === undefined || isNaN(Number(v)) ? '—' : Math.round(Number(v))+'°C' }
function load(v) { return (Number(v)||0).toFixed(2) }
function rate(v) {
    var n = Number(v)||0
    return n >= 10000 ? (n/1000).toFixed(1)+'k/s' : n.toFixed(0)+'/s'
}
function readout(m, mode) {
    if (!m || !m.warm) return '—'
    if (mode === 1) return Number(m.idlePct).toFixed(1)+'%'
    if (mode === 2) return temp(m.temp)
    if (mode === 3) return ghz(m.freq ? m.freq.avg : null)
    return Number(m.busyPct).toFixed(1)+'%'
}
function modeName(mode) { return ['% busy', '% idle', 'Temperature', 'Clock speed'][mode] || '% busy' }
function modeTag(mode) { return ['BUSY', 'IDLE', 'PACKAGE', 'CLOCK'][mode] || 'BUSY' }
