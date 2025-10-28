#include <Arduino.h>
#include <Dynamixel2Arduino.h>
#include <elapsedMillis.h>
#include <iostream>



#define DXL_SERIAL Serial1
#define DEBUG_SERIAL Serial

const int DXL_DIR_PIN = A6;
const uint8_t DID = 1;
const float DXL_PROTOCOL = 2.0;
const uint32_t DXL_BAUD = 1000000;

Dynamixel2Arduino dxl(DXL_SERIAL, DXL_DIR_PIN);

const float DEG_PER_TICK = 360.0f / 4096.0f;
const float TICK_PER_DEG = 4096.0f / 360.0f;
const float RPM_PER_VEL = 0.229;
using namespace ControlTableItem;
const int32_t checkEndStart = -2000;
const int32_t checkEndEnd = 6000;
const int32_t calibrateCurrentCCW = 1700;
const int32_t calibrateCurrentCW = 2400;
const int32_t zeroTick = 2050;
const float mercyToleranceTick = 15;
const float checkEndsToleranceDeg = 10;

int32_t stoppedTick;
float startCurrent = 180;
float calCur1, calCur2, calCur3, calCur4, calCur5;
int32_t startTick, endTick, midTick;
bool cancelled;
int32_t curPos;
float curCur;
float userRPM, RPM1, RPM2, RPM3, RPM4, RPM5;
float tarVolt = 5;
float sollDegTotal;
int32_t userGoto;

void setup(){
  Serial.begin(115200);
  dxl.begin(DXL_BAUD);
  dxl.setPortProtocolVersion(DXL_PROTOCOL);

  dxl.torqueOff(DID);
  dxl.setOperatingMode(DID, OP_EXTENDED_POSITION);
  dxl.writeControlTableItem(DRIVE_MODE, DID, 0b101);
  dxl.writeControlTableItem(HOMING_OFFSET, DID, 0);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DID, 1000);
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DID, 500);
  dxl.torqueOn(DID);
}

int32_t DegToTick(float deg){
  return deg * TICK_PER_DEG;
}

float TickToDeg(int32_t tick){
  return tick * DEG_PER_TICK;
}

uint32_t rpmToVel(float rpm){
  return round(rpm / RPM_PER_VEL);
}

int32_t getTickPosition(){
  return dxl.getPresentPosition(DID, UNIT_RAW);
}

float getDegPosition(){
  return TickToDeg(dxl.getPresentPosition(DID, UNIT_RAW));
}

uint32_t rpmToTime(int32_t goalTick, float rpm){
  uint32_t out_time = 60/rpm*1000;
  int32_t diff_pos = abs(dxl.getPresentPosition(DID, UNIT_RAW) - goalTick);
  out_time = out_time * diff_pos/4096;
  return out_time;
}

void dxlInit(){
  cancelled = false;
  calCur1 = 0;
  calCur2 = 0;
  calCur3 = 0;
  calCur4 = 0;
  calCur5 = 0;
}

/*
void driveTo(int32_t tick, float rpm, uint8_t DYN_ID = 1){
  dxl.torqueOff(DYN_ID);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DYN_ID, rpmToVel(rpm)); 
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DYN_ID, round(rpmToVel(rpm) / 3));
  dxl.torqueOn(DYN_ID);
  dxl.setGoalPosition(DYN_ID, tick, UNIT_RAW);
}*/

void driveTo(int32_t tick, float rpm, uint8_t DYN_ID = 1){
  dxl.torqueOff(DYN_ID);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DYN_ID, rpmToTime(tick, rpm)); 
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DYN_ID, 0);
  dxl.torqueOn(DYN_ID);
  dxl.setGoalPosition(DYN_ID, tick, UNIT_RAW);
}

bool reachedGoal(int32_t target_tick, uint8_t measureSpd = 0, uint8_t measureMode = 0, uint8_t error_tick = 1, uint32_t timeout = 20000, uint8_t DYN_ID = 1){
  elapsedMillis polling;
  elapsedMillis t;
  float curTolerance = 5;

  while(t < timeout && cancelled == false){
    if(polling > 5){
      curPos = getTickPosition();
      curCur = fabsf(dxl.getPresentCurrent(DID, UNIT_MILLI_AMPERE));

      if (Serial.available()) {
        String stopCommand = Serial.readStringUntil('\n');
        stopCommand.trim();
        if(stopCommand == "STOP"){
          Serial.print("Vorgang wurde abgebrochen");
          cancelled = true;
          break;
        }
      }
      if(measureMode == 0){
        switch(measureSpd){
          case 1: if(curCur > calCur1 + curTolerance){
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
          case 2: if(curCur > calCur2 + curTolerance){
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
          case 3: if(curCur > calCur3 + curTolerance){
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
          case 4: if(curCur > calCur4 + curTolerance){
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
          case 5: if(curCur > calCur5 + curTolerance){
            stoppedTick = getTickPosition();
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
          default: break;
        }
      }

      if(measureMode == 1){
        switch(measureSpd){
          case 1: if(calCur1 < curCur){calCur1 = curCur;} break;
          case 2: if(calCur2 < curCur){calCur2 = curCur;} break;
          case 3: if(calCur3 < curCur){calCur3 = curCur;} break;
          case 4: if(calCur4 < curCur){calCur4 = curCur;} break;
          case 5: if(calCur5 < curCur){calCur5 = curCur;} break;
          default: break;
        }
        if(fabsf(curCur) >= startCurrent){
          dxl.setGoalPosition(DID, curPos, UNIT_RAW);
          return false;
        }
      }

      if ((fabsf(curPos - target_tick) <= error_tick) && curPos - target_tick < 0) {
        for(int i = 0; i<5 ; i++){
          dxl.setGoalPosition(DID, getTickPosition() + 1, UNIT_RAW);
        } 
        return true;
      }
      else if ((fabsf(curPos - target_tick) <= error_tick) && curPos - target_tick > 0) {
        for(int i = 0; i<5 ; i++){
          dxl.setGoalPosition(DID, getTickPosition() - 1, UNIT_RAW);
        } 
        return true;
      }
      else if (curPos == target_tick){
        return true;
      }
      polling = 0;
    }
  }
  dxl.setGoalPosition(DID, getTickPosition(), UNIT_RAW);
  return false;
}

void calibrateCurrents(){
  for(int i = 1; i <= 5; i++){
    float calRPM = userRPM/i;
    if(i == 1){
      driveTo(calibrateCurrentCCW, calRPM);
      reachedGoal(calibrateCurrentCCW, i, 1);
      driveTo(calibrateCurrentCW, calRPM);
      reachedGoal(calibrateCurrentCW, i, 1);
    }
    driveTo(calibrateCurrentCCW, calRPM);
    reachedGoal(calibrateCurrentCCW, i, 1);
    driveTo(calibrateCurrentCW, calRPM);
    reachedGoal(calibrateCurrentCW, i, 1);
    switch(i){
      case 1: RPM1 = calRPM; break;
      case 2: RPM2 = calRPM; break;
      case 3: RPM3 = calRPM; break;
      case 4: RPM4 = calRPM; break;
      case 5: RPM5 = calRPM; break;
      default: break;
    }
  }
  driveTo(zeroTick, RPM1);
  reachedGoal(zeroTick, RPM1);
}

void checkEnds(){
  int32_t mercyStart = DegToTick(360 - sollDegTotal + checkEndsToleranceDeg);
  int32_t mercyEnd = DegToTick(sollDegTotal - checkEndsToleranceDeg);
  driveTo(mercyStart, RPM1);
  reachedGoal(mercyStart, 1);
  driveTo(checkEndStart, RPM5);
  if(reachedGoal(checkEndStart, 5) == false){
    startTick = stoppedTick;
  }
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  } 
  driveTo(mercyEnd, RPM1);
  reachedGoal(mercyEnd, 1);
  driveTo(checkEndEnd, RPM5);
  if(reachedGoal(checkEndEnd, 5) == false){
    endTick = stoppedTick;
  }
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  }
}

void sim_movement(){
  int32_t mercyStart = startTick + mercyToleranceTick;
  int32_t mercyEnd = endTick - mercyToleranceTick;
  float simRPM;
  for(int i = 1; i <= 5; i++){
    simRPM = userRPM/i;
    /*if(i == 1){
      for(int j = 0; j < 2; j++)
      {
        driveTo(mercyStart, simRPM);
        reachedGoal(mercyStart, i);
        driveTo(mercyEnd, simRPM);
        reachedGoal(mercyEnd, i);
      }
    }*/
    driveTo(mercyStart, simRPM);
    reachedGoal(mercyStart, i);
    driveTo(mercyEnd, simRPM);
    reachedGoal(mercyEnd, i);
  }
  driveTo(zeroTick, userRPM);
  reachedGoal(zeroTick);
  dxl.ledOff(DID);
}

void loop(){
  if(Serial.available()){
    String command = Serial.readStringUntil('\n');
    command.trim();

    // EINGABE VON PYTHON
    if(command.startsWith("SETV:")){tarVolt = command.substring(5).toFloat();}
    if(command.startsWith("SETW:")){sollDegTotal = command.substring(5).toFloat();}
    if(command.startsWith("SETS:")){userRPM = command.substring(5).toFloat();}

    if(command.startsWith("goto:")){userGoto = command.substring(5).toFloat();}

    else if(command == "GO"){
      dxlInit();
      calibrateCurrents();
      checkEnds();

      if(cancelled == false){
        Serial.println("READY");
      } else{
        Serial.println("CANCEL");
        cancelled = false;
      }
      while(true){
        String s = Serial.readStringUntil('\n');
        s.trim();
        delay(0.2);
        if(s == "START"){
          sim_movement();
          break;
        }
      }
      Serial.println("FINISH");
    }
  }
}
