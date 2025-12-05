#include <Arduino.h>
#include <Dynamixel2Arduino.h>
#include <elapsedMillis.h>

// --------------- DYNAMIXEL VARIABLES
#define DXL_SERIAL Serial1
#define DEBUG_SERIAL Serial

const int DXL_DIR_PIN = A6;
const uint8_t DID = 1;
const float DXL_PROTOCOL = 2.0;
const uint32_t DXL_BAUD = 1000000;

Dynamixel2Arduino dxl(DXL_SERIAL, DXL_DIR_PIN);

// --------------- VARIABLES
const float DEG_PER_TICK = 360.0f / 4096.0f;
const float TICK_PER_DEG = 4096.0f / 360.0f;
const float RPM_PER_VEL = 0.229;
using namespace ControlTableItem;
const int32_t CHECK_END_START = -2000;
const int32_t CHECK_END_END = 6000;
const int32_t CALIBRATE_CURRENT_CCW = 1700;
const int32_t CALIBRATE_CURRENT_CW = 2400;
const int32_t ZERO_TICK = 2050;
const float MERCY_TOLERANCE_TICK = 15;
const float CHECK_ENDS_TOL_DEG = 10;

int32_t stopped_tick;
float start_current = 180;
float cal_cur0, cal_cur1, cal_cur2, cal_cur3;
float cur_tolerance = 5;
int32_t start_tick, end_tick, mid_tick;
int32_t sim_mercy_start, sim_mercy_end;
bool cancelled;
int32_t cur_pos;
float cur_cur;
float slow_rpm = 5;
float user_rpm, rpm1, rpm2, rpm3;
float real_time1 = 0, real_time2 = 0, real_time3 = 0;
float theo_time1 = 0, theo_time2 = 0, theo_time3 = 0;
float target_deg_total;
int32_t user_go_to;
float delay1, delay2, delay3;


// --------------- SETUP AND ASSIST FUNCTIONS
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

int32_t deg_to_tick(float deg){
  return deg * TICK_PER_DEG;
}

float tick_to_deg(int32_t tick){
  return tick * DEG_PER_TICK;
}

int32_t get_tick_position(){
  return dxl.getPresentPosition(DID, UNIT_RAW);
}

float get_deg_position(){
  return tick_to_deg(dxl.getPresentPosition(DID, UNIT_RAW));
}

uint32_t rpm_to_time(int32_t goal_tick, float rpm){
  uint32_t out_time = 60/rpm*1000;
  int32_t diff_pos = abs(dxl.getPresentPosition(DID, UNIT_RAW) - goal_tick);
  out_time = out_time * diff_pos/4096;
  return out_time;
}


// --------------- INIT FUNCTION
void dxl_init(){
  cancelled = false;
  cal_cur0 = 0;
  cal_cur1 = 0;
  cal_cur2 = 0;
  cal_cur3 = 0;
}


// --------------- DRIVE FUNCTIONS
void drive_to(int32_t tick, float rpm, uint8_t DYN_ID = 1){
  dxl.torqueOff(DYN_ID);
  dxl.writeControlTableItem(PROFILE_VELOCITY, DYN_ID, rpm_to_time(tick, rpm)); 
  dxl.writeControlTableItem(PROFILE_ACCELERATION, DYN_ID, 0);
  dxl.torqueOn(DYN_ID);
  dxl.setGoalPosition(DYN_ID, tick, UNIT_RAW);
}

bool reached_goal(int32_t target_tick, uint8_t measure_spd = 0, uint8_t measure_mode = 0, uint8_t error_tick = 1, uint32_t timeout = 20000, uint8_t DYN_ID = 1){
  elapsedMillis polling;
  elapsedMillis t;

  while(t < timeout && cancelled == false){
    if(polling > 5){
      cur_pos = get_tick_position();
      cur_cur = fabsf(dxl.getPresentCurrent(DID, UNIT_MILLI_AMPERE));

      if (Serial.available()) {
        String stop_command = Serial.readStringUntil('\n');
        stop_command.trim();
        if(stop_command == "STOP"){
          Serial.println("Vorgang wurde abgebrochen");
          cancelled = true;
          break;
        }
      }
      if(measure_mode == 0){
        switch(measure_spd){
          case 0: if(cur_cur > cal_cur0 + cur_tolerance){
            stopped_tick = get_tick_position();
            dxl.setGoalPosition(DID, cur_pos, UNIT_RAW);
            return false;} 
            break;
          case 1: if(cur_cur > cal_cur1 + cur_tolerance){
            dxl.setGoalPosition(DID, cur_pos, UNIT_RAW);
            return false;} 
            break;
          case 2: if(cur_cur > cal_cur2 + cur_tolerance){
            dxl.setGoalPosition(DID, cur_pos, UNIT_RAW);
            return false;} 
            break;
          case 3: if(cur_cur > cal_cur3 + cur_tolerance){
            dxl.setGoalPosition(DID, cur_pos, UNIT_RAW);
            return false;} 
            break;
          default: break;
        }
      }

      if(measure_mode == 1){
        switch(measure_spd){
          case 0: if(cal_cur0 < cur_cur){cal_cur0 = cur_cur;} break;
          case 1: if(cal_cur1 < cur_cur){cal_cur1 = cur_cur;} break;
          case 2: if(cal_cur2 < cur_cur){cal_cur2 = cur_cur;} break;
          case 3: if(cal_cur3 < cur_cur){cal_cur3 = cur_cur;} break;
          default: break;
        }
        if(fabsf(cur_cur) >= start_current){
          dxl.setGoalPosition(DID, cur_pos, UNIT_RAW);
          return false;
        }
      }

      if ((fabsf(cur_pos - target_tick) <= error_tick) && cur_pos - target_tick < 0) {
        for(int i = 0; i<5 ; i++){
          dxl.setGoalPosition(DID, get_tick_position() + 1, UNIT_RAW);
        } 
        return true;
      }
      else if ((fabsf(cur_pos - target_tick) <= error_tick) && cur_pos - target_tick > 0) {
        for(int i = 0; i<5 ; i++){
          dxl.setGoalPosition(DID, get_tick_position() - 1, UNIT_RAW);
        } 
        return true;
      }
      else if (cur_pos == target_tick){
        return true;
      }
      polling = 0;
    }
  }
  dxl.setGoalPosition(DID, get_tick_position(), UNIT_RAW);
  return false;
}


// --------------- MOVEMENT FUNCTIONS
void calibrate_currents(){
  float real_time1, real_time2, real_time3;
  float theo_time1, theo_time2, theo_time3;
  drive_to(CALIBRATE_CURRENT_CW, user_rpm);
  reached_goal(CALIBRATE_CURRENT_CW, 2, 1);

  drive_to(CALIBRATE_CURRENT_CCW, slow_rpm);
  reached_goal(CALIBRATE_CURRENT_CCW, 0, 1);
  drive_to(CALIBRATE_CURRENT_CW, slow_rpm);
  reached_goal(CALIBRATE_CURRENT_CW, 0, 1);

  for(int i = 1; i <= 3; i++){
    float rpm_intervall = user_rpm/2;
    float cal_rpm = rpm_intervall*i;
    elapsedMillis cur_millis;
    drive_to(CALIBRATE_CURRENT_CCW, cal_rpm);
    reached_goal(CALIBRATE_CURRENT_CCW, i, 1);
    drive_to(CALIBRATE_CURRENT_CW, cal_rpm);
    reached_goal(CALIBRATE_CURRENT_CW, i, 1);
    switch(i){
      case 1: rpm1 = cal_rpm; real_time1 = cur_millis; 
              theo_time1 = rpm_to_time(CALIBRATE_CURRENT_CCW, cal_rpm); 
              break;
      case 2: rpm2 = cal_rpm; real_time2 = cur_millis; 
              theo_time2 = rpm_to_time(CALIBRATE_CURRENT_CCW, cal_rpm);
              break;
      case 3: rpm3 = cal_rpm; real_time3 = cur_millis; 
              theo_time3 = rpm_to_time(CALIBRATE_CURRENT_CCW, cal_rpm); 
              break;
      default: break;
    }
  }
  delay1 = (real_time1 - 2*theo_time1)/1000; // ms -> s
  delay2 = (real_time2 - 2*theo_time2)/1000;
  delay3 = (real_time3 - 2*theo_time3)/1000;

  Serial.print("DELAY1");
  Serial.println(delay1);
  Serial.print("DELAY2");
  Serial.println(delay2);
  Serial.print("DELAY3");
  Serial.println(delay3);
  drive_to(ZERO_TICK, rpm1);
  reached_goal(ZERO_TICK, rpm1);
}

void check_ends(){
  int32_t check_mercy_start = deg_to_tick(360 - target_deg_total + CHECK_ENDS_TOL_DEG);
  int32_t check_mercy_end = deg_to_tick(target_deg_total - CHECK_ENDS_TOL_DEG);
  drive_to(check_mercy_start, rpm3);
  reached_goal(check_mercy_start, 3);
  drive_to(CHECK_END_START, slow_rpm);
  if(reached_goal(CHECK_END_START, 0) == false){
    start_tick = stopped_tick;
  }
  for(int i = 0; i < 5; i++){
    dxl.ledOff(1);
    delay(100);
     dxl.ledOn(1);
    delay(100);
  } 
  drive_to(check_mercy_end, rpm3);
  reached_goal(check_mercy_end, 3);
  drive_to(CHECK_END_END, slow_rpm);
  if(reached_goal(CHECK_END_END, 0) == false){
    end_tick = stopped_tick;
  }

  sim_mercy_start = start_tick + MERCY_TOLERANCE_TICK;
  sim_mercy_end = end_tick - MERCY_TOLERANCE_TICK;
  uint32_t sim_distance = abs(sim_mercy_end - sim_mercy_start);
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
  float sim_rpm;
  float rpm_intervall; 

  drive_to(sim_mercy_end, user_rpm/2);
  reached_goal(sim_mercy_end, 1);
  for(int i = 1; i <= 3; i++){
    rpm_intervall = user_rpm/2;
    sim_rpm = rpm_intervall * i;

    drive_to(sim_mercy_start, sim_rpm);
    reached_goal(sim_mercy_start, i);
    drive_to(sim_mercy_end, sim_rpm);
    reached_goal(sim_mercy_end, i);
  }
  Serial.println("FINISH");
}

void go_zero(){
  drive_to(ZERO_TICK, user_rpm);
  reached_goal(ZERO_TICK, 2);
  
  Serial.println("READY");
}

// --------------- LOOP
void loop(){
  if(Serial.available()){
    String command = Serial.readStringUntil('\n');
    command.trim();

    // EINGABE VON PYTHON
    if(command.startsWith("SETW:")){target_deg_total = command.substring(5).toFloat();}
    if(command.startsWith("SETS:")){user_rpm = command.substring(5).toFloat();}

    if(command.startsWith("goto:")){user_go_to = command.substring(5).toFloat();}

    if(command == "ZERO"){
      go_zero();
    }
    
    if(command == "GO"){
      dxl_init();
      calibrate_currents();
      check_ends();

      if(cancelled == false){
        Serial.println("READY");
      } else{
        Serial.println("CANCEL");
        cancelled = false;
      }
    }
    if(command == "START"){
      sim_movement();

      if(cancelled == true){
        Serial.println("CANCEL");
        cancelled = false;
      }
      drive_to(ZERO_TICK, user_rpm);
      reached_goal(ZERO_TICK, 2);
      dxl.ledOff(DID);
    }
  }
}
