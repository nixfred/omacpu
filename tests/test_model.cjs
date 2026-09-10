const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path'),os=require('os');
const ctx={Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}};
// Values built inside the vm carry that realm's prototypes, so deepEqual sees
// them as structurally identical but not reference-equal. Compare by shape.
const same=(a,b)=>assert.equal(JSON.stringify(a),JSON.stringify(b));
vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'..','Model.js'),'utf8').replace('.pragma library',''),ctx);
const m={warm:true,busyPct:84.375,idlePct:15.625,temp:66.4,freq:{avg:3212345}};
assert.equal(ctx.readout(m,0),'84.4%');assert.equal(ctx.readout(m,1),'15.6%');
assert.equal(ctx.readout(m,2),'66°C');assert.equal(ctx.readout(m,3),'3.21 GHz');
assert.equal(ctx.readout({warm:true,busyPct:1,idlePct:99,temp:null,freq:{avg:null}},2),'—');
for(const [p,c] of [[0,[133,13,41]],[50,[239,204,69]],[100,[67,242,161]]]){
  const result=ctx.ramp(p);c.forEach((v,i)=>assert.equal(Math.round(result[i]*255),v));
}
assert.equal(ctx.readout({},0),'—');
assert.equal(ctx.readout({warm:false,busyPct:50},0),'—');
assert.equal(ctx.ghz(5400000),'5.40 GHz');
assert.equal(ctx.rate(15419.7),'15.4k/s');assert.equal(ctx.rate(117.7),'118/s');
assert.equal(ctx.load(10.16),'10.16');
assert.equal(ctx.modeTag(3),'CLOCK');

// ── theme palette ──────────────────────────────────────────────────────────
// A theme names its palette directly or as terminal colour slots, and may ship
// both. The named key wins; quoting and trailing comments are tolerated.
const named=`mode = "dark"\naccent = "#42E8F5"\nred = "#FF5964"\nyellow = "#F6C84D"\ngreen = "#8BCB68"\norange = "#FF8A55"\n`;
const slots=`color1 = "#FF5964"  # red\ncolor2='#8BCB68'\ncolor3 = #F6C84D\n`;
same(ctx.parsePalette(named),{red:'#FF5964',yellow:'#F6C84D',green:'#8BCB68',orange:'#FF8A55'});
same(ctx.parsePalette(slots),{red:'#FF5964',yellow:'#F6C84D',green:'#8BCB68'});
assert.equal(ctx.parsePalette(named+`color1 = "#000000"\n`).red,'#FF5964');
same(ctx.parsePalette(''),{});

// A well-separated theme replaces the built-in ramp outright. A stop already
// above the chroma floor passes through untouched -- red and yellow here are
// exactly what the theme wrote.
const namedStops=ctx.rampStops(named);
same(namedStops[0],[255,89,100]);
same(namedStops[1],[246,200,77]);
const eternia=ctx.ramp(50,namedStops);
same(eternia.slice(0,3).map(v=>Math.round(v*255)),[246,200,77]);
// Its green sits at 0.49 saturation, just under the floor, so it is nudged up
// rather than passed through or thrown away.
same(namedStops[2],[137,209,98]);

// A theme whose stops are muted but genuinely different hues is lifted, not
// rejected: 2-haxorz's three sit 14, 85 and 178 degrees apart and only its
// chroma was missing. Rejecting it wholesale left the die off-theme.
const muddy=`red = "#b9968f"\nyellow = "#7b8768"\ngreen = "#708c8b"\n`;
const lifted=ctx.rampStops(muddy);
assert.notEqual(lifted,ctx.DEFAULT_STOPS);
same(lifted,[[214,131,114],[134,185,54],[57,195,190]]);
assert.ok(ctx.separation(lifted[0],lifted[1])>=80);
assert.ok(ctx.separation(lifted[1],lifted[2])>=80);

// Stops that are one colour stay rejected, because no amount of saturation
// pulls them apart: blue-red-4k-warm's yellow and green differ by one step of
// red.
const oneStep=`red = "#b88485"\nyellow = "#e99b8c"\ngreen = "#ea9b8c"\n`;
assert.equal(ctx.rampStops(oneStep),ctx.DEFAULT_STOPS);

// A greyscale theme has no hue to preserve and borrows the built-in hues.
const grey=`red = "#8a8a8a"\nyellow = "#a0a0a0"\ngreen = "#b4b4b4"\n`;
const greyStops=ctx.rampStops(grey);
assert.notEqual(greyStops,ctx.DEFAULT_STOPS);
assert.ok(ctx.separation(greyStops[0],greyStops[1])>=80);
// A partial palette is not a palette.
assert.equal(ctx.rampStops(`red = "#FF5964"\ngreen = "#8BCB68"\n`),ctx.DEFAULT_STOPS);
assert.equal(ctx.rampStops(''),ctx.DEFAULT_STOPS);
// Stops are only honoured as a complete set of three.
same(ctx.ramp(0,[[1,2,3]]),ctx.ramp(0));

// The temperature trace takes the theme's orange only when it stays clear of
// the ramp's hot end, and always as #RRGGBB — QML's color type reads hex and
// SVG names, and silently yields black for a CSS rgb() string.
const heat=ctx.heatColor(named,ctx.rampStops(named));
assert.match(heat,/^#[0-9A-Fa-f]{6}$/);
assert.equal(heat,'#FF8A55');
assert.equal(ctx.heatColor(`red = "#FF5964"\norange = "#FF5A65"\n`,[[255,89,100],[246,200,77],[139,203,104]]),ctx.DEFAULT_HEAT);
assert.equal(ctx.heatColor('',null),ctx.DEFAULT_HEAT);

// Every installed theme is either usable as a ramp or falls back cleanly; none
// may produce a partial or malformed set of stops. Skipped where no themes are
// installed, so the suite still runs on a bare checkout.
// Both directories: the user's own themes and the ones Omarchy installs.
// Checking only the first misses more than half of them.
let checked=0;
for(const themeDir of [path.join(os.homedir(),'.config/omarchy/themes'),'/usr/share/omarchy/themes']){
  if(!fs.existsSync(themeDir)) continue;
  for(const name of fs.readdirSync(themeDir)){
    const file=path.join(themeDir,name,'colors.toml');
    if(!fs.existsSync(file)) continue;
    const stops=ctx.rampStops(fs.readFileSync(file,'utf8'));
    assert.equal(stops.length,3,name);
    for(const stop of stops){
      assert.equal(stop.length,3,name);
      stop.forEach(v=>assert.ok(Number.isInteger(v)&&v>=0&&v<=255,name+' '+v));
    }
    assert.match(ctx.heatColor(fs.readFileSync(file,'utf8'),stops),/^#[0-9A-Fa-f]{6}$/,name);
    checked++;
  }
}
console.log('Readout formats, cold telemetry, units, red/yellow/green endpoints,'
  +' theme palette parsing and the ramp contrast guard pass'
  +(checked?' ('+checked+' installed themes checked).':'.'));
