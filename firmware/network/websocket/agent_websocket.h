#pragma once

#include <Arduino.h>
#include <WebSocketsClient.h>

#include "audio/pcm_player.h"
#include "behavior/motion_expression_controller.h"
#include "network/wifi/wifi_manager.h"
#include "sensor/motion/motion_detector.h"

namespace mimi {
namespace network {

class AgentWebSocket {
 public:
  AgentWebSocket(WifiManager& wifi, audio::PcmPlayer& pcm_player);

  void begin(const char* ssid, const char* password, const char* host,
             uint16_t port, const char* path, const char* device_id);
  void loop();

  bool connected() const;
  bool consume_speech_start(const char* event_id);
  bool consume_speech_end(const char* event_id);
  bool consume_no_speech(const char* event_id);
  bool consume_speech_stop(const char* event_id);
  bool consume_playback_end(const char* event_id);
  void release_speech_audio();
  const String& last_event_id() const;
  bool send_motion_event(
      sensor::motion::MotionState state, behavior::BehaviorMode behavior_mode,
      const sensor::motion::MotionFeatures& features, uint32_t timestamp_ms);
  bool send_touch_event(uint32_t timestamp_ms);
  bool send_sensor_telemetry(
      const sensor::motion::Mpu6050Sample& sample,
      sensor::motion::MotionState state, behavior::BehaviorMode behavior_mode,
      const sensor::motion::MotionFeatures& features, bool touch_active,
      uint32_t timestamp_ms);

 private:
  static AgentWebSocket* active_instance_;
  static void on_websocket_event(WStype_t type, uint8_t* payload,
                                 size_t length);

  void handle_event(WStype_t type, uint8_t* payload, size_t length);
  void handle_text(uint8_t* payload, size_t length);
  void handle_speech_start(const char* speech_id, const char* event_id,
                           int sample_rate, int channels);
  void handle_speech_end(const char* speech_id);
  void handle_speech_stop(const char* speech_id, const char* event_id,
                          const char* reason);
  void handle_motion_ack(const char* event_id, bool will_speak);
  void send_speech_ready();
  void send_speech_playback_end();
  void send_hello();

  WifiManager& wifi_;
  audio::PcmPlayer& pcm_player_;
  WebSocketsClient websocket_;
  String host_;
  String path_;
  String device_id_;
  uint16_t port_ = 8765;
  bool websocket_started_ = false;
  bool connected_ = false;
  bool receiving_speech_ = false;
  bool speech_audio_released_ = false;
  bool speech_end_pending_ = false;
  bool speech_start_ready_ = false;
  bool speech_end_ready_ = false;
  bool no_speech_ready_ = false;
  bool speech_stop_ready_ = false;
  bool playback_end_ready_ = false;
  static constexpr size_t PRECOMMIT_AUDIO_CAPACITY = 4096;
  uint8_t precommit_audio_[PRECOMMIT_AUDIO_CAPACITY] = {};
  size_t precommit_audio_length_ = 0;
  String speech_start_event_id_;
  String speech_end_event_id_;
  String no_speech_event_id_;
  String speech_stop_event_id_;
  String playback_end_event_id_;
  String last_event_id_;
  String speech_event_id_;
  String speech_id_;
};

}  // namespace network
}  // namespace mimi
