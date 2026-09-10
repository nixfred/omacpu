.pragma library

// Built-in load ramp: dark red with no headroom, yellow at half, green when
// idle. Used verbatim whenever the active theme has no palette we can read, or
// has one whose three stops are too close together to read as a scale.
var DEFAULT_STOPS = [[133, 13, 41], [239, 204, 69], [67, 242, 161]]
var DEFAULT_HEAT = '#ffa86b'

// Themes name their palette either directly or as terminal colour slots. The
// named key wins where a theme defines both, so it leads each list.
var PALETTE_ALIASES = {red: ['red', 'color1'], yellow: ['yellow', 'color3'],
                       green: ['green', 'color2'], orange: ['orange', 'color11']}

// How far apart the ramp's three stops must sit before a theme's own colours
// replace the built-in ones. Chosen from the installed themes that ship a
// palette: their worst adjacent separations run 2, 59, 59, 91, 106, ...  so a
// floor of 80 rejects the handful that would break the die.
//
// Separation is measured after lifting, not before. A theme like 2-haxorz
// scores 59 raw -- three desaturated tones that all read as the same
// grey-brown -- yet its three hues are 14, 85 and 178 degrees apart and only
// its chroma was missing. Rejecting it wholesale threw away a usable palette;
// lifting it first and then measuring keeps the theme's own hues. What still
// fails after lifting genuinely is one colour: blue-red-4k-warm scores 2
// because its yellow (#e99b8c) and green (#ea9b8c) differ by one step of red,
// and no amount of saturation will pull those apart.
var RAMP_SEPARATION_MIN = 80

// Chroma the ramp needs to read as a warning at a glance. A stop below the hue
// floor has no hue worth preserving and borrows the built-in one rather than
// tinting grey at random.
//
// The lightness band is deliberately wide. Its job is to rescue a stop so dark
// or so pale it disappears, not to second-guess a theme that chose a bright
// red on purpose; a narrower band dimmed perfectly good vivid palettes.
var RAMP_MIN_SAT = 0.55
var RAMP_MIN_LIGHT = 0.30
var RAMP_MAX_LIGHT = 0.78
var RAMP_HUE_FLOOR = 0.12

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v) || 0)) }

function hexToRgb(hex) {
    var m = /^#([0-9a-fA-F]{6})$/.exec(String(hex || '').replace(/^\s+|\s+$/g, ''))
    if (!m) return null
    var n = parseInt(m[1], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

// Weighted RGB distance ("redmean"), a cheap stand-in for a perceptual metric.
// Accurate enough to tell three distinct hues from three shades of one mud,
// which is the only judgement the ramp needs it to make.
function separation(a, b) {
    var mean = (a[0] + b[0]) / 2, dr = a[0] - b[0], dg = a[1] - b[1], db = a[2] - b[2]
    return Math.sqrt((2 + mean / 256) * dr * dr + 4 * dg * dg + (2 + (255 - mean) / 256) * db * db)
}

// The shell surfaces only foreground, background, accent, urgent and muted, so
// a theme's green and yellow have to come from the colors.toml it ships.
function parsePalette(raw) {
    var found = {}, lines = String(raw || '').split('\n')
    for (var i = 0; i < lines.length; i++) {
        var m = /^\s*([A-Za-z0-9_]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})/.exec(lines[i])
        if (m) found[m[1].toLowerCase()] = m[2]
    }
    var out = {}
    for (var role in PALETTE_ALIASES) {
        var keys = PALETTE_ALIASES[role]
        for (var k = 0; k < keys.length; k++) {
            if (found[keys[k]]) { out[role] = found[keys[k]]; break }
        }
    }
    return out
}

function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255
    var mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, h = 0, s = 0
    if (mx !== mn) {
        var d = mx - mn
        s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
        if (mx === r) h = (g - b) / d + (g < b ? 6 : 0)
        else if (mx === g) h = (b - r) / d + 2
        else h = (r - g) / d + 4
        h /= 6
    }
    return [h, s, l]
}

function hslToRgb(h, s, l) {
    if (s === 0) return [Math.round(l * 255), Math.round(l * 255), Math.round(l * 255)]
    var hi = l < 0.5 ? l * (1 + s) : l + s - l * s
    var lo = 2 * l - hi
    function channel(t) {
        if (t < 0) t += 1
        if (t > 1) t -= 1
        if (t < 1/6) return lo + (hi - lo) * 6 * t
        if (t < 1/2) return hi
        if (t < 2/3) return lo + (hi - lo) * (2/3 - t) * 6
        return lo
    }
    return [Math.round(channel(h + 1/3) * 255), Math.round(channel(h) * 255), Math.round(channel(h - 1/3) * 255)]
}

// Raise one stop to the chroma and lightness the ramp needs while keeping the
// hue the theme chose. Half the installed themes ship a palette that is the
// right three hues at the wrong three saturations.
function liftStop(rgb, builtin) {
    var a = rgbToHsl(rgb[0], rgb[1], rgb[2])
    var b = rgbToHsl(builtin[0], builtin[1], builtin[2])
    var hue = a[1] < RAMP_HUE_FLOOR ? b[0] : a[0]
    return hslToRgb(hue, Math.max(a[1], RAMP_MIN_SAT),
                    Math.min(Math.max(a[2], RAMP_MIN_LIGHT), RAMP_MAX_LIGHT))
}

// Three stops for the load ramp: the theme's own hues, lifted to a readable
// chroma, and DEFAULT_STOPS only when even lifted they do not separate.
function rampStops(raw) {
    var palette = parsePalette(raw)
    var low = hexToRgb(palette.red), mid = hexToRgb(palette.yellow), high = hexToRgb(palette.green)
    if (!low || !mid || !high) return DEFAULT_STOPS
    low = liftStop(low, DEFAULT_STOPS[0])
    mid = liftStop(mid, DEFAULT_STOPS[1])
    high = liftStop(high, DEFAULT_STOPS[2])
    if (separation(low, mid) < RAMP_SEPARATION_MIN) return DEFAULT_STOPS
    if (separation(mid, high) < RAMP_SEPARATION_MIN) return DEFAULT_STOPS
    return [low, mid, high]
}

// The temperature trace rides alongside the busy trace, so it only takes the
// theme's orange when that stays clear of the ramp's hot end.
function heatColor(raw, stops) {
    var hex = parsePalette(raw).orange, orange = hexToRgb(hex)
    if (!orange) return DEFAULT_HEAT
    if (separation(orange, (stops || DEFAULT_STOPS)[0]) < RAMP_SEPARATION_MIN) return DEFAULT_HEAT
    // Hex, not rgb(): QML's color type parses #RRGGBB and SVG names, and
    // silently yields black for a CSS functional notation.
    return hex
}

// Colour follows headroom: the ramp's low stop with none, its mid at half, its
// high when idle.
function ramp(percent, stops) {
    var s = stops && stops.length === 3 ? stops : DEFAULT_STOPS
    var f = clamp(percent, 0, 100) / 100
    var a = f <= 0.5 ? s[0] : s[1]
    var b = f <= 0.5 ? s[1] : s[2]
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
