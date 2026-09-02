#pragma once

#include <Arduino.h>
#include <driver/i2s.h>

#include "config/pins.h"

namespace mimi {
namespace audio {

// Plays the Agent's mono, little-endian, 16-bit PCM stream through a
// MAX98357A. The MAX98357A receives I2S TX data only, so this class uses the
// ESP-IDF legacy driver in TX-only mode instead of Arduino's duplex I2SClass.
// Each mono sample is duplicated to left and right for the amplifier's stereo
// frame format.
class PcmPlayer {
 public:
  bool begin(uint32_t sample_rate_hz);
  bool start(uint32_t sample_rate_hz);
  void finish();
  bool poll_drained();
  void stop();

  size_t write(const uint8_t* data, size_t length);
  bool ready() const;
  bool playing() const;

 private:
  static constexpr size_t MONO_SAMPLES_PER_WRITE = 256;

  bool initialize(uint32_t sample_rate_hz);
  void shutdown_driver();
  void reset_carry();

  int16_t stereo_buffer_[MONO_SAMPLES_PER_WRITE * 2] = {};
  uint32_t sample_rate_hz_ = 0;
  bool initialized_ = false;
  bool playing_ = false;
  bool input_finished_ = false;
  uint32_t drain_ready_at_ms_ = 0;
  bool has_carry_byte_ = false;
  uint8_t carry_byte_ = 0;
};

}  // namespace audio
}  // namespace mimi
