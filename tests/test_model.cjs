const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const ctx={Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}};
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
console.log('Readout formats, cold telemetry, units, and red/yellow/green endpoints pass.');
