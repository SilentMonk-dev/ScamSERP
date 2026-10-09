const test=require('node:test');
const assert=require('node:assert/strict');
const {LocationTracker}=require('../scamserp/static/location-tracker.js');
test('one persistent watcher delivers successive positions without network or storage',()=>{
  let calls=0,success,options;const positions=[];
  const tracker=new LocationTracker({geolocation:{watchPosition(fn,err,o){calls++;success=fn;options=o;return 42;},clearWatch(){}},onPosition:p=>positions.push(p),onStatus(){}});
  tracker.start();tracker.start();
  success({coords:{latitude:20,longitude:75,accuracy:10},timestamp:100});
  success({coords:{latitude:20.001,longitude:75.001,accuracy:8},timestamp:200});
  assert.equal(calls,1);assert.equal(positions.length,2);assert.equal(tracker.position.timestamp,200);assert.equal(options.enableHighAccuracy,true);
});
test('denied permission stops watching and can be retried without pretending location exists',()=>{
  let fail,cleared;const statuses=[];
  const tracker=new LocationTracker({geolocation:{watchPosition(fn,error){fail=error;return 7;},clearWatch(id){cleared=id;}},onPosition(){assert.fail('no location without permission');},onStatus:s=>statuses.push(s)});
  tracker.start();fail({code:1});assert.equal(cleared,7);assert.equal(tracker.watchId,null);assert.ok(statuses.includes('denied'));assert.equal(tracker.position,null);tracker.start();assert.equal(tracker.watchId,7);
});
test('page cleanup releases a watcher; invalid coordinates are not shown',()=>{
  let success,cleared=0;const tracker=new LocationTracker({geolocation:{watchPosition(fn){success=fn;return 1;},clearWatch(){cleared++;}},onPosition(){assert.fail('invalid location');},onStatus(){}});
  tracker.start();success({coords:{latitude:NaN,longitude:75},timestamp:1});tracker.stop();tracker.stop();assert.equal(cleared,1);
});
