'use strict';
// Injectable browser adapter keeps continuous location behavior testable without
// requesting or fabricating a real device location in automated tests.
class LocationTracker {
  constructor({geolocation, onPosition, onStatus}) {
    this.geolocation=geolocation; this.onPosition=onPosition; this.onStatus=onStatus;
    this.watchId=null; this.position=null;
  }
  start() {
    if(this.watchId!==null) return;
    if(!this.geolocation){this.onStatus('unavailable');return;}
    this.onStatus('requesting');
    this.watchId=this.geolocation.watchPosition(position=>{
      const c=position.coords;
      if(!Number.isFinite(c.latitude)||!Number.isFinite(c.longitude)||Math.abs(c.latitude)>90||Math.abs(c.longitude)>180)return;
      this.position={lat:c.latitude,lng:c.longitude,accuracy:c.accuracy,timestamp:position.timestamp};
      this.onPosition(this.position); this.onStatus('active');
    },error=>{
      this.onStatus(error.code===1?'denied':error.code===2?'unavailable':'timeout');
      if(error.code===1)this.stop();
    },{enableHighAccuracy:true,timeout:15000,maximumAge:5000});
  }
  stop() {
    if(this.watchId!==null){this.geolocation.clearWatch(this.watchId);this.watchId=null;}
  }
}
if(typeof module!=='undefined')module.exports={LocationTracker};
