#include <Arduino.h>
#include <Dynamixel2Arduino.h>
#include <elapsedMillis.h>

#define DXL_SERIAL Serial1
#define DEBUG_SERIAL Serial

const int DXL_DIR_PIN = A6;
const uint8_t DID = 1;
const float DXL_PROTOCOL = 2.0;
const uint32_t DXL_BAUD = 1000000;

Dynamixel2Arduino dxl(DXL_SERIAL, DXL_DIR_PIN);

const float DEG_PER_TICK = 360.0f / 4096.0f;
const uint8_t TICK_PER_DEG = 4096 / 360;
const float RPM_PER_VEL = 0.229;
using namespace ControlTableItem;
const int32_t calibrateStart = -2000;
const int32_t calibrateEnd = 6000;

float startCurrent = 150;
float calCur1, calCur2, calCur3, calCur4;
uint32_t startTick, endTick;
bool cancelled;
int32_t curpos;

void setup(){
  Serial.begin(115200);
  dxl.begin(DXL_BAUD);
  dxl.setPortProtocolVersion(DXL_PROTOCOL);

  dxl.torqueOff(DID);
  dxl.setOperatingMode(DID, OP_EXTENDED_POSITION);
  dxl.writeControlTableItem(DRIVE_MODE, DID, 1);
  dxl.writeControlTableItem(HOMING_OFFSET, DID, 0);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DID, 40);
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DID, 15);
  dxl.torqueOn(DID);
}

int32_t DegToTick(float deg){
  return deg * TICK_PER_DEG;
}

float TickToDeg(uint8_t tick){
  return tick * DEG_PER_TICK;
}

uint32_t rpmToVel(int rpm){
  return round(rpm / RPM_PER_VEL);
}

int32_t getTickPosition(){
  return dxl.getPresentPosition(DID, UNIT_RAW);
}

float getDegPosition(){
  return TickToDeg(dxl.getPresentPosition(DID, UNIT_RAW));
}

void driveTo(uint8_t tick, int rpm, uint8_t DYN_ID = 1){
  dxl.torqueOff(DYN_ID);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DYN_ID, rpmToVel(rpm)); 
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DYN_ID, round(rpmToVel(rpm) / 3));
  dxl.torqueOn(DYN_ID);
  dxl.setGoalPosition(DYN_ID, tick, UNIT_RAW);
}

bool reachedGoal(int32_t target_tick, uint8_t error_tick = 1, uint32_t timeout = 20000, uint8_t DYN_ID = 1){
  elapsedMillis polling;
  elapsedMillis t;

  while(t < timeout && cancelled == false){
    if(polling < 5){
      curpos = getTickPosition();

      if (Serial.available()) {
        String stopCommand = Serial.readStringUntil('\n');
        stopCommand.trim();
        if(stopCommand == "STOP"){
          Serial.print("Vorgang wurde abgebrochen");
          cancelled = true;
          break;
        }
      }
    }
  }
}

void checkEnds(){
  driveTo(calibrateStart, 30);
  if(reachedGoal(calibrateStart) == false){
    startTick = getTickPosition();
  }
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  } 
  driveTo(calibrateEnd, 30);
  if(reachedGoal(calibrateEnd) == false){
    endTick = getTickPosition();
  }
}

void sim_movement(){

}

void loop(){
  sim_movement();
}
