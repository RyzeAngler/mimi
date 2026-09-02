#include <Arduino.h>

#include "audio/pcm_player.h"
#include "behavior/motion_expression_controller.h"
#include "config/debug.h"
#include "config/network.h"
#include "config/pins.h"
#include "config/display.h"
#include "expression/roboeyes/roboeyes_face.h"
#include "hal/i2c_bus/i2c_bus.h"
#include "network/websocket/agent_websocket.h"
#include "network/wifi/wifi_manager.h"
#include "sensor/motion/motion_detector.h"
#include "sensor/motion/mpu6050/mpu6050.h"
#include "sensor/touch/ttp223.h"

namespace {
unsigned long last_heartbeat_ms = 0;
unsigned long heartbeat_count = 0;
mimi::hal::I2cBus i2c_bus;
mimi::expression::RoboEyesFace face;
mimi::sensor::motion::Mpu6050 mpu6050;
mimi::sensor::motion::MotionDetector motion_detector;
mimi::sensor::touch::Ttp223 touch_sensor;
mimi::behavior::MotionExpressionController expression_controller;
mimi::audio::PcmPlayer pcm_player;
mimi::network::WifiManager wifi_manager;
mimi::network::AgentWebSocket agent_websocket(wifi_manager, pcm_player);
bool motion_sensor_ready = false;
bool reaction_waiting_for_speech = false;
bool reaction_speaking = false;
bool pending_touch_visual = false;
mimi::sensor::motion::MotionState pending_visual_state =
    mimi::sensor::motion::MotionState::Level;
mimi::sensor::motion::MotionFeatures pending_visual_features;
uint32_t pending_visual_timestamp_ms = 0;
String pending_visual_event_id;

bool is_agent_motion_event(mimi::sensor::motion::MotionState state) {
  using mimi::sensor::motion::MotionState;
  return state == MotionState::TiltLeft || state == MotionState::TiltRight ||
         state == MotionState::TiltForward ||
         state == MotionState::TiltBackward || state == MotionState::Shaking;
}
}

void setup() {
  Serial.begin(115200);

  const unsigned long serial_wait_start = millis();
  while (!Serial && millis() - serial_wait_start < 1500) {
    delay(10);
  }

  Serial.println();
  Serial.println("Mimi firmware booting");
  Serial.printf("I2C candidate pins: SDA=%d, SCL=%d\n", mimi::pins::I2C_SDA,
                mimi::pins::I2C_SCL);

  i2c_bus.begin(mimi::pins::I2C_SDA, mimi::pins::I2C_SCL,
                mimi::pins::I2C_FREQUENCY_HZ);
  i2c_bus.scan(Serial, mimi::pins::I2C_SDA, mimi::pins::I2C_SCL);

  if (face.begin(mimi::display::DEFAULT_ADDRESS)) {
    Serial.printf("OLED ready at 0x%02X\n", face.address());
  } else {
    Serial.println("OLED not detected; continuing without display");
  }

  motion_sensor_ready =
      mpu6050.begin(i2c_bus.wire(), mimi::pins::MPU6050_ADDRESS);
  if (motion_sensor_ready) {
    Serial.printf("MPU6050 ready at 0x%02X, WHO_AM_I=0x%02X\n",
                  mpu6050.address(), mpu6050.who_am_i());
  } else {
    Serial.println("MPU6050 not detected; continuing without motion input");
  }

  touch_sensor.begin(mimi::pins::TOUCH_SIG, mimi::pins::TOUCH_ACTIVE_HIGH,
                     mimi::pins::TOUCH_DEBOUNCE_MS);
  Serial.printf("TTP223 ready: SIG=GPIO%d active=%s debounce=%lums\n",
                touch_sensor.signal_pin(),
                mimi::pins::TOUCH_ACTIVE_HIGH ? "HIGH" : "LOW",
                static_cast<unsigned long>(mimi::pins::TOUCH_DEBOUNCE_MS));

  Serial.println("I2S player initializing");
  if (pcm_player.begin(16000)) {
    Serial.printf("I2S player ready: BCLK=%d LRCLK=%d DOUT=%d\n",
                  mimi::pins::I2S_BCLK, mimi::pins::I2S_LRCLK,
                  mimi::pins::I2S_DOUT);
  } else {
    Serial.println("I2S player unavailable; continuing without audio");
  }

  agent_websocket.begin(
      mimi::network_config::WIFI_SSID, mimi::network_config::WIFI_PASSWORD,
      mimi::network_config::AGENT_HOST, mimi::network_config::AGENT_PORT,
      mimi::network_config::AGENT_PATH, mimi::network_config::DEVICE_ID);

  Serial.println("Mimi firmware ready");
}

void loop() {
  const unsigned long now = millis();
  agent_websocket.loop();

  if (reaction_waiting_for_speech &&
      agent_websocket.consume_speech_start(pending_visual_event_id.c_str())) {
    expression_controller.begin_speaking(
        pending_visual_state, pending_visual_features, pending_touch_visual,
        now, face);
    agent_websocket.release_speech_audio();
    reaction_waiting_for_speech = false;
    reaction_speaking = true;
    Serial.printf("reaction speaking event=%s visual=%s\n",
                  pending_visual_event_id.c_str(),
                  pending_touch_visual ? "touch" : "motion");
  }

  if ((reaction_waiting_for_speech || reaction_speaking) &&
      agent_websocket.consume_speech_stop(pending_visual_event_id.c_str())) {
    expression_controller.cancel_reaction(motion_detector.features(), now,
                                           face);
    reaction_waiting_for_speech = false;
    reaction_speaking = false;
    pending_touch_visual = false;
    pending_visual_event_id = "";
    Serial.println("reaction cancelled; returned to idle");
  }

  if (reaction_speaking &&
      agent_websocket.consume_speech_end(pending_visual_event_id.c_str())) {
    expression_controller.begin_draining();
    Serial.printf("reaction draining event=%s\n",
                  pending_visual_event_id.c_str());
  }

  if (reaction_waiting_for_speech &&
      agent_websocket.consume_no_speech(pending_visual_event_id.c_str())) {
    expression_controller.cancel_reaction(motion_detector.features(), now,
                                           face);
    reaction_waiting_for_speech = false;
    pending_touch_visual = false;
    pending_visual_event_id = "";
    Serial.println("reaction had no speech; returned to idle");
  }

  if (reaction_speaking &&
      agent_websocket.consume_playback_end(pending_visual_event_id.c_str())) {
    expression_controller.finish_reaction(motion_detector.features(), now,
                                           face);
    reaction_speaking = false;
    pending_touch_visual = false;
    Serial.printf("reaction playback complete event=%s; returned to idle\n",
                  pending_visual_event_id.c_str());
    pending_visual_event_id = "";
  }

  const auto touch_transition = touch_sensor.update(now);
  if (touch_transition == mimi::sensor::touch::TouchTransition::Pressed) {
    Serial.printf("touch: pressed pin=%d\n", touch_sensor.signal_pin());

    // Thinking is committed immediately after the Agent accepts the event;
    // the touch reaction itself waits for speech_start so OLED and audio begin
    // together.
    if (!reaction_waiting_for_speech && !reaction_speaking &&
        agent_websocket.connected() &&
        agent_websocket.send_touch_event(now)) {
      reaction_waiting_for_speech = true;
      pending_touch_visual = true;
      pending_visual_timestamp_ms = now;
      pending_visual_event_id = agent_websocket.last_event_id();
      expression_controller.begin_thinking(now, face);
      Serial.printf("touch thinking event=%s until speech_start\n",
                    pending_visual_event_id.c_str());
    } else {
      Serial.println("touch ignored while a reaction is active or Agent is offline");
    }
  } else if (touch_transition ==
             mimi::sensor::touch::TouchTransition::Released) {
    Serial.println("touch: released");
  }
  if (now - last_heartbeat_ms >= 1000) {
    last_heartbeat_ms = now;
    ++heartbeat_count;
    Serial.printf("heartbeat: %lu\n", heartbeat_count);
  }

  static unsigned long last_motion_read_ms = 0;
  static unsigned long last_motion_telemetry_ms = 0;
  static mimi::sensor::motion::MotionState last_motion_state =
      mimi::sensor::motion::MotionState::Level;
  static mimi::sensor::motion::MotionState last_agent_motion_state =
      mimi::sensor::motion::MotionState::Level;
  if (motion_sensor_ready &&
      now - last_motion_read_ms >= mimi::pins::MPU6050_READ_INTERVAL_MS) {
    last_motion_read_ms = now;
    mimi::sensor::motion::Mpu6050Sample sample;
    if (mpu6050.read(sample)) {
      const auto motion_state = motion_detector.update(sample, now);
      if (motion_state == mimi::sensor::motion::MotionState::Level) {
        // A new physical action may use the same direction as the previous
        // one, but only after the detector has observed a real neutral point.
        // This rearms event emission without sending repeated events while a
        // board is held in one position.
        last_agent_motion_state =
            mimi::sensor::motion::MotionState::Level;
      }

      if (is_agent_motion_event(motion_state) &&
          motion_state != last_agent_motion_state &&
          !reaction_waiting_for_speech && !reaction_speaking &&
          agent_websocket.connected()) {
        if (agent_websocket.send_motion_event(
                motion_state,
                expression_controller.reaction_mode(motion_state,
                                                    motion_detector.features()),
                motion_detector.features(), now)) {
          reaction_waiting_for_speech = true;
          pending_touch_visual = false;
          pending_visual_state = motion_state;
          pending_visual_features = motion_detector.features();
          pending_visual_timestamp_ms = now;
          pending_visual_event_id = agent_websocket.last_event_id();
          last_agent_motion_state = motion_state;
          expression_controller.begin_thinking(now, face);
          Serial.printf("motion thinking event=%s until speech_start\n",
                        pending_visual_event_id.c_str());
        }
      }

      if (!reaction_waiting_for_speech && !reaction_speaking) {
        expression_controller.update(motion_state, motion_detector.features(),
                                     now, face);
      }
      if (motion_state != last_motion_state) {
        Serial.printf("motion: %s\n",
                      mimi::sensor::motion::motion_state_name(motion_state));
        last_motion_state = motion_state;
      }

      if (mimi::debug::ENABLE_MOTION_TELEMETRY &&
          now - last_motion_telemetry_ms >=
              mimi::debug::MOTION_TELEMETRY_INTERVAL_MS) {
        last_motion_telemetry_ms = now;
        Serial.printf(
            "imu ax=%+.2f ay=%+.2f az=%+.2f g "
            "gx=%+.1f gy=%+.1f gz=%+.1f dps "
            "roll=%+.1f pitch=%+.1f speed=%.1f intensity=%.2f "
            "state=%s behavior=%s visual=%s oled=%s mood=%s pos=%s effect=%s\n",
            sample.accel_x_g, sample.accel_y_g, sample.accel_z_g,
            sample.gyro_x_dps, sample.gyro_y_dps, sample.gyro_z_dps,
            motion_detector.features().roll_deg,
            motion_detector.features().pitch_deg,
            motion_detector.features().angular_speed_dps,
            motion_detector.features().motion_intensity,
            mimi::sensor::motion::motion_state_name(motion_state),
            mimi::behavior::behavior_mode_name(expression_controller.mode()),
            mimi::behavior::visual_state_name(expression_controller.visual_state()),
            face.ready() ? "ready" : "offline",
            mimi::expression::mood_name(face.mood()),
            mimi::expression::position_name(face.position()),
            mimi::expression::effect_name(face.last_effect()));
        agent_websocket.send_sensor_telemetry(
            sample, motion_state, expression_controller.mode(),
            motion_detector.features(), touch_sensor.touched(), now);
      }
    }
  }

  face.update();
}
