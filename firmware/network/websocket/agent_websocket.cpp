#include "agent_websocket.h"

#include <ArduinoJson.h>

namespace mimi {
namespace network {

AgentWebSocket* AgentWebSocket::active_instance_ = nullptr;

AgentWebSocket::AgentWebSocket(WifiManager& wifi, audio::PcmPlayer& pcm_player)
    : wifi_(wifi), pcm_player_(pcm_player) {
  active_instance_ = this;
}

void AgentWebSocket::begin(const char* ssid, const char* password,
                           const char* host, uint16_t port, const char* path,
                           const char* device_id) {
  host_ = host == nullptr ? "" : host;
  path_ = path == nullptr || path[0] == '\0' ? "/" : path;
  device_id_ = device_id == nullptr ? "mimi-c3" : device_id;
  port_ = port;
  wifi_.begin(ssid, password);
}

void AgentWebSocket::loop() {
  wifi_.loop();
  if (!wifi_.connected()) {
    if (websocket_started_) {
      websocket_.disconnect();
      websocket_started_ = false;
      connected_ = false;
    }
    return;
  }

  if (!websocket_started_) {
    if (host_.isEmpty()) {
      return;
    }
    websocket_.begin(host_.c_str(), port_, path_.c_str());
    websocket_.onEvent(AgentWebSocket::on_websocket_event);
    websocket_.setReconnectInterval(5000);
    websocket_.enableHeartbeat(15000, 5000, 2);
    websocket_started_ = true;
    Serial.printf("Agent WebSocket connecting to ws://%s:%u%s\n",
                  host_.c_str(), port_, path_.c_str());
  }
  websocket_.loop();

  if (speech_end_pending_ && speech_audio_released_ &&
      pcm_player_.poll_drained()) {
    send_speech_playback_end();
    receiving_speech_ = false;
    speech_audio_released_ = false;
    speech_end_pending_ = false;
    playback_end_ready_ = true;
    playback_end_event_id_ = speech_event_id_;
    speech_event_id_ = "";
    speech_id_ = "";
    Serial.println("Speech playback drained");
  }
}

bool AgentWebSocket::connected() const { return connected_; }

bool AgentWebSocket::consume_speech_start(const char* event_id) {
  if (!speech_start_ready_ ||
      !speech_start_event_id_.equals(event_id == nullptr ? "" : event_id)) {
    return false;
  }
  speech_start_ready_ = false;
  speech_start_event_id_ = "";
  return true;
}

bool AgentWebSocket::consume_speech_end(const char* event_id) {
  if (!speech_end_ready_ ||
      !speech_end_event_id_.equals(event_id == nullptr ? "" : event_id)) {
    return false;
  }
  speech_end_ready_ = false;
  speech_end_event_id_ = "";
  return true;
}

bool AgentWebSocket::consume_no_speech(const char* event_id) {
  if (!no_speech_ready_ ||
      !no_speech_event_id_.equals(event_id == nullptr ? "" : event_id)) {
    return false;
  }
  no_speech_ready_ = false;
  no_speech_event_id_ = "";
  return true;
}

bool AgentWebSocket::consume_speech_stop(const char* event_id) {
  if (!speech_stop_ready_ ||
      !speech_stop_event_id_.equals(event_id == nullptr ? "" : event_id)) {
    return false;
  }
  speech_stop_ready_ = false;
  speech_stop_event_id_ = "";
  return true;
}

bool AgentWebSocket::consume_playback_end(const char* event_id) {
  if (!playback_end_ready_ ||
      !playback_end_event_id_.equals(event_id == nullptr ? "" : event_id)) {
    return false;
  }
  playback_end_ready_ = false;
  playback_end_event_id_ = "";
  return true;
}

const String& AgentWebSocket::last_event_id() const {
  return last_event_id_;
}

void AgentWebSocket::release_speech_audio() {
  if (!receiving_speech_ || speech_audio_released_) {
    return;
  }
  speech_audio_released_ = true;
  send_speech_ready();
  if (precommit_audio_length_ > 0) {
    pcm_player_.write(precommit_audio_, precommit_audio_length_);
    precommit_audio_length_ = 0;
  }
  if (speech_end_pending_) {
    pcm_player_.finish();
  }
}

bool AgentWebSocket::send_motion_event(
    sensor::motion::MotionState state, behavior::BehaviorMode behavior_mode,
    const sensor::motion::MotionFeatures& features, uint32_t timestamp_ms) {
  if (!connected_) {
    return false;
  }

  char event_id[32];
  snprintf(event_id, sizeof(event_id), "evt-%lu",
           static_cast<unsigned long>(timestamp_ms));
  last_event_id_ = event_id;
  speech_event_id_ = event_id;

  char message[768];
  const int written = snprintf(
      message, sizeof(message),
      "{\"type\":\"motion_event\",\"event_id\":\"evt-%lu\","
      "\"event\":\"%s\",\"behavior\":\"%s\","
      "\"intensity\":%.3f,\"timestamp_ms\":%lu,"
      "\"roll_deg\":%.2f,\"pitch_deg\":%.2f,"
      "\"angular_speed_dps\":%.2f,\"acceleration_norm_g\":%.3f,"
      "\"dynamic_acceleration_g\":%.3f,\"stability\":%.3f,"
      "\"tilt_strength\":%.3f,\"peak_angular_speed_dps\":%.2f,"
      "\"peak_dynamic_acceleration_g\":%.3f,\"confidence\":%.3f,"
      "\"still_duration_ms\":%lu,\"state_duration_ms\":%lu,"
      "\"motion_duration_ms\":%lu}",
      static_cast<unsigned long>(timestamp_ms),
      sensor::motion::motion_state_name(state),
      behavior::behavior_mode_name(behavior_mode), features.motion_intensity,
      static_cast<unsigned long>(timestamp_ms), features.roll_deg,
      features.pitch_deg, features.angular_speed_dps,
      features.acceleration_norm_g, features.dynamic_acceleration_g,
      features.stability, features.tilt_strength,
      features.peak_angular_speed_dps,
      features.peak_dynamic_acceleration_g, features.confidence,
      static_cast<unsigned long>(features.still_duration_ms),
      static_cast<unsigned long>(features.state_duration_ms),
      static_cast<unsigned long>(features.motion_duration_ms));
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(message)) {
    last_event_id_ = "";
    return false;
  }
  websocket_.sendTXT(message);
  Serial.printf("Agent motion event: %s\n", message);
  return true;
}

bool AgentWebSocket::send_touch_event(uint32_t timestamp_ms) {
  if (!connected_) {
    return false;
  }

  char event_id[32];
  snprintf(event_id, sizeof(event_id), "evt-touch-%lu",
           static_cast<unsigned long>(timestamp_ms));
  last_event_id_ = event_id;
  speech_event_id_ = event_id;

  char message[256];
  const int written = snprintf(
      message, sizeof(message),
      "{\"type\":\"motion_event\",\"event_id\":\"evt-touch-%lu\","
      "\"event\":\"touch\",\"behavior\":\"happy\","
      "\"intensity\":1.000,\"timestamp_ms\":%lu}",
      static_cast<unsigned long>(timestamp_ms),
      static_cast<unsigned long>(timestamp_ms));
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(message)) {
    last_event_id_ = "";
    return false;
  }
  websocket_.sendTXT(message);
  Serial.printf("Agent touch event: %s\n", message);
  return true;
}

bool AgentWebSocket::send_sensor_telemetry(
    const sensor::motion::Mpu6050Sample& sample,
    sensor::motion::MotionState state, behavior::BehaviorMode behavior_mode,
    const sensor::motion::MotionFeatures& features, bool touch_active,
    uint32_t timestamp_ms) {
  if (!connected_) {
    return false;
  }

  char message[1024];
  const int written = snprintf(
      message, sizeof(message),
      "{\"type\":\"sensor_telemetry\",\"timestamp_ms\":%lu,"
      "\"accel_x_g\":%.3f,\"accel_y_g\":%.3f,\"accel_z_g\":%.3f,"
      "\"gyro_x_dps\":%.2f,\"gyro_y_dps\":%.2f,\"gyro_z_dps\":%.2f,"
      "\"roll_deg\":%.2f,\"pitch_deg\":%.2f,"
      "\"angular_speed_dps\":%.2f,\"motion_intensity\":%.3f,"
      "\"acceleration_norm_g\":%.3f,\"dynamic_acceleration_g\":%.3f,"
      "\"stability\":%.3f,\"tilt_strength\":%.3f,"
      "\"peak_angular_speed_dps\":%.2f,"
      "\"peak_dynamic_acceleration_g\":%.3f,\"confidence\":%.3f,"
      "\"still_duration_ms\":%lu,\"state_duration_ms\":%lu,"
      "\"motion_duration_ms\":%lu,"
      "\"state\":\"%s\",\"behavior\":\"%s\","
      "\"touch_active\":%s}",
      static_cast<unsigned long>(timestamp_ms), sample.accel_x_g,
      sample.accel_y_g, sample.accel_z_g, sample.gyro_x_dps,
      sample.gyro_y_dps, sample.gyro_z_dps, features.roll_deg,
      features.pitch_deg, features.angular_speed_dps,
      features.motion_intensity, features.acceleration_norm_g,
      features.dynamic_acceleration_g, features.stability,
      features.tilt_strength, features.peak_angular_speed_dps,
      features.peak_dynamic_acceleration_g, features.confidence,
      static_cast<unsigned long>(features.still_duration_ms),
      static_cast<unsigned long>(features.state_duration_ms),
      static_cast<unsigned long>(features.motion_duration_ms),
      sensor::motion::motion_state_name(state),
      behavior::behavior_mode_name(behavior_mode),
      touch_active ? "true" : "false");
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(message)) {
    return false;
  }
  websocket_.sendTXT(message);
  return true;
}

void AgentWebSocket::on_websocket_event(WStype_t type, uint8_t* payload,
                                        size_t length) {
  if (active_instance_ != nullptr) {
    active_instance_->handle_event(type, payload, length);
  }
}

void AgentWebSocket::handle_event(WStype_t type, uint8_t* payload,
                                  size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      connected_ = true;
      Serial.println("Agent WebSocket connected");
      send_hello();
      break;

    case WStype_DISCONNECTED:
      connected_ = false;
      if (receiving_speech_ || speech_start_ready_ ||
          !speech_event_id_.isEmpty()) {
        speech_stop_ready_ = true;
        speech_stop_event_id_ = speech_event_id_.isEmpty()
                                    ? last_event_id_
                                    : speech_event_id_;
      }
      receiving_speech_ = false;
      speech_audio_released_ = false;
      speech_end_pending_ = false;
      precommit_audio_length_ = 0;
      speech_start_ready_ = false;
      speech_end_ready_ = false;
      no_speech_ready_ = false;
      playback_end_ready_ = false;
      pcm_player_.stop();
      speech_event_id_ = "";
      speech_id_ = "";
      Serial.println("Agent WebSocket disconnected");
      break;

    case WStype_TEXT:
      handle_text(payload, length);
      break;

    case WStype_BIN:
      if (receiving_speech_) {
        if (speech_audio_released_) {
          pcm_player_.write(payload, length);
        } else if (precommit_audio_length_ + length <=
                   PRECOMMIT_AUDIO_CAPACITY) {
          memcpy(precommit_audio_ + precommit_audio_length_, payload, length);
          precommit_audio_length_ += length;
        } else {
          Serial.println("Speech precommit buffer full; dropping PCM frame");
        }
      }
      break;

    default:
      break;
  }
}

void AgentWebSocket::handle_text(uint8_t* payload, size_t length) {
  JsonDocument document;
  const DeserializationError error = deserializeJson(document, payload, length);
  if (error) {
    Serial.printf("Agent JSON error: %s\n", error.c_str());
    return;
  }

  const char* type = document["type"] | "";
  if (strcmp(type, "hello_ack") == 0) {
    Serial.println("Agent hello acknowledged");
  } else if (strcmp(type, "motion_ack") == 0) {
    handle_motion_ack(document["event_id"] | "",
                      document["will_speak"] | false);
  } else if (strcmp(type, "speech_start") == 0) {
    handle_speech_start(document["speech_id"] | "", document["event_id"] | "",
                        document["sample_rate"] | 16000,
                        document["channels"] | 1);
  } else if (strcmp(type, "speech_end") == 0) {
    handle_speech_end(document["speech_id"] | "");
  } else if (strcmp(type, "speech_cancel") == 0) {
    handle_speech_stop(document["speech_id"] | "", "", "cancelled");
  } else if (strcmp(type, "speech_error") == 0) {
    handle_speech_stop(document["speech_id"] | "",
                       document["event_id"] | "", "server error");
    Serial.printf("Agent speech error: %s\n",
                  document["message"] | "unknown error");
  }
}

void AgentWebSocket::handle_speech_start(const char* speech_id,
                                         const char* event_id, int sample_rate,
                                         int channels) {
  if (channels != 1 || sample_rate <= 0) {
    Serial.printf("Unsupported speech format: rate=%d channels=%d\n",
                  sample_rate, channels);
    speech_stop_ready_ = true;
    speech_stop_event_id_ = event_id == nullptr || event_id[0] == '\0'
                                ? last_event_id_
                                : event_id;
    return;
  }
  receiving_speech_ = pcm_player_.start(static_cast<uint32_t>(sample_rate));
  speech_audio_released_ = false;
  speech_end_pending_ = false;
  speech_start_ready_ = false;
  speech_start_event_id_ = "";
  speech_end_ready_ = false;
  speech_end_event_id_ = "";
  playback_end_ready_ = false;
  playback_end_event_id_ = "";
  precommit_audio_length_ = 0;
  speech_id_ = speech_id == nullptr ? "" : speech_id;
  const bool has_event_id = event_id != nullptr && event_id[0] != '\0';
  const bool event_matches = has_event_id && last_event_id_.equals(event_id);
  speech_event_id_ = has_event_id ? event_id : "";
  if (event_matches) {
    speech_start_ready_ = receiving_speech_;
    speech_start_event_id_ = speech_event_id_;
  } else if (receiving_speech_) {
    // Manual analysis and stale event correlations aren't tied to an active
    // visual reaction. Release their PCM immediately instead of leaving it in
    // the small precommit buffer forever.
    release_speech_audio();
  }
  if (!receiving_speech_) {
    speech_stop_ready_ = true;
    speech_stop_event_id_ = speech_event_id_;
  }
  Serial.printf("Speech start id=%s rate=%d player=%s mode=%s\n",
                speech_id_.c_str(), sample_rate,
                receiving_speech_ ? "ready" : "offline",
                event_matches ? "event" : "direct");
}

void AgentWebSocket::handle_speech_end(const char* speech_id) {
  if (!receiving_speech_ ||
      !speech_id_.equals(speech_id == nullptr ? "" : speech_id)) {
    return;
  }
  // ``speech_end`` means that the Agent has sent every PCM frame. The
  // amplifier may still be draining the I2S DMA queue, so keep the speech
  // session alive until loop() can publish playback_end. This flag must be
  // set in both timing orders: speech_end may arrive before or after the
  // main loop releases the precommit audio buffer.
  speech_end_pending_ = true;
  if (!speech_audio_released_) {
    speech_end_ready_ = true;
    speech_end_event_id_ = speech_event_id_;
    return;
  }
  pcm_player_.finish();
  speech_end_ready_ = true;
  speech_end_event_id_ = speech_event_id_;
  Serial.printf("Speech end id=%s\n", speech_id_.c_str());
}

void AgentWebSocket::handle_speech_stop(const char* speech_id,
                                        const char* event_id,
                                        const char* reason) {
  const bool matches_speech =
      receiving_speech_ &&
      speech_id_.equals(speech_id == nullptr ? "" : speech_id);
  const bool matches_event =
      event_id != nullptr && event_id[0] != '\0' &&
      speech_event_id_.equals(event_id);
  if (!matches_speech && !matches_event) {
    return;
  }
  if (receiving_speech_) {
    pcm_player_.stop();
  }
  receiving_speech_ = false;
  speech_audio_released_ = false;
  speech_end_pending_ = false;
  speech_end_ready_ = false;
  speech_end_event_id_ = "";
  precommit_audio_length_ = 0;
  speech_stop_ready_ = true;
  speech_stop_event_id_ = event_id != nullptr && event_id[0] != '\0'
                              ? event_id
                              : speech_event_id_;
  speech_event_id_ = "";
  Serial.printf("Speech stop id=%s reason=%s\n", speech_id_.c_str(), reason);
}

void AgentWebSocket::handle_motion_ack(const char* event_id, bool will_speak) {
  if (event_id == nullptr || !last_event_id_.equals(event_id)) {
    return;
  }
  if (!will_speak) {
    no_speech_ready_ = true;
    no_speech_event_id_ = event_id;
    speech_event_id_ = "";
  }
  Serial.printf("Agent motion ack event=%s will_speak=%s\n", event_id,
                will_speak ? "yes" : "no");
}

void AgentWebSocket::send_speech_ready() {
  if (!connected_ || speech_id_.isEmpty()) {
    return;
  }
  char message[128];
  snprintf(message, sizeof(message),
           "{\"type\":\"speech_ready\",\"speech_id\":\"%s\"}",
           speech_id_.c_str());
  websocket_.sendTXT(message);
}

void AgentWebSocket::send_speech_playback_end() {
  if (!connected_ || speech_id_.isEmpty()) {
    return;
  }
  char message[144];
  snprintf(
      message, sizeof(message),
      "{\"type\":\"speech_playback_end\",\"speech_id\":\"%s\"}",
      speech_id_.c_str());
  websocket_.sendTXT(message);
}

void AgentWebSocket::send_hello() {
  char message[256];
  snprintf(message, sizeof(message),
           "{\"type\":\"hello\",\"device_id\":\"%s\","
           "\"protocol\":\"mimi.v1\",\"audio\":{\"format\":\"pcm_s16le\","
           "\"sample_rate\":16000,\"channels\":1},"
           "\"capabilities\":[\"speech_ready\",\"speech_playback_end\"]}",
           device_id_.c_str());
  websocket_.sendTXT(message);
}

}  // namespace network
}  // namespace mimi
