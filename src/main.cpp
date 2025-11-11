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
int32_t sim_mercyStart, sim_mercyEnd;
const float mercyToleranceTick = 15;
const float checkEndsToleranceDeg = 10;


int32_t stoppedTick;
float startCurrent = 180;
float calCur0, calCur1, calCur2, calCur3;
int32_t startTick, endTick, midTick;
bool cancelled;
int32_t curPos;
float curCur;
float slowRPM = 5;
float userRPM, RPM1, RPM2, RPM3;
float tarVolt = 5;
float sollDegTotal;
int32_t userGoto;
float delay1, delay2, delay3;

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

  dxl.ledOn(DID);
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
  calCur0 = 0;
  calCur1 = 0;
  calCur2 = 0;
  calCur3 = 0;
}

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
          case 0: if(curCur > calCur0 + curTolerance){
            stoppedTick = getTickPosition();
            dxl.setGoalPosition(DID, curPos, UNIT_RAW);
            return false;} 
            break;
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
          default: break;
        }
      }

      if(measureMode == 1){
        switch(measureSpd){
          case 0: if(calCur0 < curCur){calCur0 = curCur;} break;
          case 1: if(calCur1 < curCur){calCur1 = curCur;} break;
          case 2: if(calCur2 < curCur){calCur2 = curCur;} break;
          case 3: if(calCur3 < curCur){calCur3 = curCur;} break;
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
  float realtime1, realtime2, realtime3;
  float theotime1, theotime2, theotime3;
  driveTo(calibrateCurrentCW, userRPM);
  reachedGoal(calibrateCurrentCW, 2, 1);

  driveTo(calibrateCurrentCCW, slowRPM);
  reachedGoal(calibrateCurrentCCW, 0, 1);
  driveTo(calibrateCurrentCW, slowRPM);
  reachedGoal(calibrateCurrentCW, 0, 1);

  for(int i = 1; i <= 3; i++){
    float rpmIntervall = userRPM/2;
    float calRPM = rpmIntervall*i;
    elapsedMillis curMillis;
    driveTo(calibrateCurrentCCW, calRPM);
    reachedGoal(calibrateCurrentCCW, i, 1);
    driveTo(calibrateCurrentCW, calRPM);
    reachedGoal(calibrateCurrentCW, i, 1);
    switch(i){
      case 1: RPM1 = calRPM; realtime1 = curMillis; 
              theotime1 = rpmToTime(calibrateCurrentCCW, calRPM); 
              break;
      case 2: RPM2 = calRPM; realtime2 = curMillis; 
              theotime2 = rpmToTime(calibrateCurrentCCW, calRPM);
              break;
      case 3: RPM3 = calRPM; realtime3 = curMillis; 
              theotime3 = rpmToTime(calibrateCurrentCCW, calRPM); 
              break;
      default: break;
    }
  }
  delay1 = (realtime1 - 2*theotime1)/1000; // ms -> s
  delay2 = (realtime2 - 2*theotime2)/1000;
  delay3 = (realtime3 - 2*theotime3)/1000;

  Serial.print("DELAY1");
  Serial.println(delay1);
  Serial.print("DELAY2");
  Serial.println(delay2);
  Serial.print("DELAY3");
  Serial.println(delay3);
  driveTo(zeroTick, RPM1);
  reachedGoal(zeroTick, RPM1);
}

void checkEnds(){
  int32_t check_mercyStart = DegToTick(360 - sollDegTotal + checkEndsToleranceDeg);
  int32_t check_mercyEnd = DegToTick(sollDegTotal - checkEndsToleranceDeg);
  driveTo(check_mercyStart, RPM3);
  reachedGoal(check_mercyStart, 3);
  driveTo(checkEndStart, slowRPM);
  if(reachedGoal(checkEndStart, 0) == false){
    startTick = stoppedTick;
  }
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  } 
  driveTo(check_mercyEnd, RPM3);
  reachedGoal(check_mercyEnd, 3);
  driveTo(checkEndEnd, slowRPM);
  if(reachedGoal(checkEndEnd, 0) == false){
    endTick = stoppedTick;
  }

  sim_mercyStart = startTick + mercyToleranceTick;
  sim_mercyEnd = endTick - mercyToleranceTick;
  uint32_t sim_distance = abs(sim_mercyEnd - sim_mercyStart);
  Serial.print("ANGLE");
  Serial.println(sim_distance);
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  }
}

void sim_movement(){
  float simRPM;
  float rpmIntervall; 

  driveTo(sim_mercyEnd, userRPM/2);
  reachedGoal(sim_mercyEnd, 1);
  for(int i = 1; i <= 3; i++){
    rpmIntervall = userRPM/2;
    simRPM = rpmIntervall * i;

    driveTo(sim_mercyStart, simRPM);
    reachedGoal(sim_mercyStart, i);
    driveTo(sim_mercyEnd, simRPM);
    reachedGoal(sim_mercyEnd, i);
  }
  Serial.println("FINISH");
}

void test_movement(){
  float testRPM;
  float rpmint;

  driveTo(4096, userRPM);
  reachedGoal(4096, 2);
  
  for(int i = 1; i<= 3; i++){
    
    rpmint = userRPM/2;
    testRPM = rpmint * i;
    elapsedMillis curmillis;
    driveTo(0, testRPM);
    reachedGoal(0, i);
    driveTo(4096, testRPM);
    reachedGoal(4096, i);


    

  }
  /*
  int32_t timearr[] = {time1, time2, time3};
  Serial.print("TIME");
  Serial.println(timearr[0]);
  Serial.print("TIM2");
  Serial.println(timearr[1]);
  Serial.print("TIM3");
  Serial.println(timearr[2]);
  */
  Serial.println("FINISH");
  
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

    if(command == "GO"){
      dxlInit();
      calibrateCurrents();
      checkEnds();

      if(cancelled == false){
        Serial.println("READY");
      } else{
        Serial.println("CANCEL");
        cancelled = false;
      }
    }
    if(command == "START"){
      sim_movement();

      driveTo(zeroTick, userRPM);
      reachedGoal(zeroTick, 2);
      dxl.ledOff(DID);
    }
  }
}
