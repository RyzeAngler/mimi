#include "pcm_player.h"

namespace mimi {
namespace audio {

namespace {
constexpr int32_t kVolumeNumerator = 2;
constexpr int32_t kVolumeDenominator = 3;

int16_t scale_sample(int16_t sample) {
  return static_cast<int16_t>(
      static_cast<int32_t>(sample) * kVolumeNumerator /
      kVolumeDenominator);
}
}  // namespace

bool PcmPlayer::begin(uint32_t sample_rate_hz) {
  if (initialized_ && sample_rate_hz_ == sample_rate_hz) {
    return true;
  }
  if (initialized_) {
    shutdown_driver();
  }
  return initialize(sample_rate_hz);
}

bool PcmPlayer::initialize(uint32_t sample_rate_hz) {
  if (sample_rate_hz == 0) {
    return false;
  }

  // Keep the DMA chunks bounded so a speech_cancel can stop promptly. The
  // Arduino I2SClass initializes RX|TX duplex mode on this target, even
  // though MAX98357A only needs TX. That path can stall ESP32-C3 startup.
  // Install the legacy ESP-IDF driver explicitly in TX-only mode instead.
  i2s_config_t i2s_config = {};
  i2s_config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  i2s_config.sample_rate = sample_rate_hz;
  i2s_config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  i2s_config.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  i2s_config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  i2s_config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL2;
  i2s_config.dma_buf_count = 4;
  i2s_config.dma_buf_len = 256;
  i2s_config.use_apll = false;
  i2s_config.tx_desc_auto_clear = true;

  const esp_err_t install_result =
      i2s_driver_install(I2S_NUM_0, &i2s_config, 0, nullptr);
  if (install_result != ESP_OK) {
    Serial.printf("I2S driver install failed: 0x%08X\n",
                  static_cast<unsigned int>(install_result));
    initialized_ = false;
    sample_rate_hz_ = 0;
    playing_ = false;
    reset_carry();
    return false;
  }

  i2s_pin_config_t pin_config = {};
  pin_config.mck_io_num = I2S_PIN_NO_CHANGE;
  pin_config.bck_io_num = pins::I2S_BCLK;
  pin_config.ws_io_num = pins::I2S_LRCLK;
  pin_config.data_out_num = pins::I2S_DOUT;
  pin_config.data_in_num = I2S_PIN_NO_CHANGE;

  const esp_err_t pin_result = i2s_set_pin(I2S_NUM_0, &pin_config);
  if (pin_result != ESP_OK) {
    Serial.printf("I2S pin setup failed: 0x%08X\n",
                  static_cast<unsigned int>(pin_result));
    i2s_driver_uninstall(I2S_NUM_0);
    initialized_ = false;
    sample_rate_hz_ = 0;
    playing_ = false;
    reset_carry();
    return false;
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  initialized_ = true;
  sample_rate_hz_ = initialized_ ? sample_rate_hz : 0;
  playing_ = false;
  input_finished_ = false;
  drain_ready_at_ms_ = 0;
  reset_carry();
  return initialized_;
}

bool PcmPlayer::start(uint32_t sample_rate_hz) {
  // Reinitializing the driver discards any queued audio from a previous
  // speech, which makes the server's speech_cancel observable immediately.
  if (initialized_) {
    shutdown_driver();
  }
  if (!initialize(sample_rate_hz)) {
    Serial.printf("I2S init failed, sample_rate=%lu\n",
                  static_cast<unsigned long>(sample_rate_hz));
    return false;
  }
  playing_ = true;
  input_finished_ = false;
  return true;
}

void PcmPlayer::finish() {
  if (has_carry_byte_) {
    Serial.println("I2S dropped an incomplete PCM sample at speech end");
  }
  reset_carry();
  input_finished_ = true;
  // ESP32-C3's legacy I2S header does not expose a non-blocking DMA drain
  // query. The configured four 256-frame DMA buffers represent this much
  // audio at the current sample rate; add a small guard for the amplifier
  // output stage and poll it from the main loop.
  const uint32_t dma_tail_ms =
      static_cast<uint32_t>((4UL * 256UL * 1000UL) / sample_rate_hz_);
  drain_ready_at_ms_ = millis() + dma_tail_ms + 16;
}

bool PcmPlayer::poll_drained() {
  if (!playing_ || !input_finished_) {
    return false;
  }

  if (static_cast<int32_t>(millis() - drain_ready_at_ms_) < 0) {
    return false;
  }

  playing_ = false;
  input_finished_ = false;
  drain_ready_at_ms_ = 0;
  return true;
}

void PcmPlayer::stop() {
  if (initialized_) {
    shutdown_driver();
  }
  initialized_ = false;
  playing_ = false;
  input_finished_ = false;
  drain_ready_at_ms_ = 0;
  sample_rate_hz_ = 0;
  reset_carry();
}

size_t PcmPlayer::write(const uint8_t* data, size_t length) {
  if (!initialized_ || !playing_ || input_finished_ || data == nullptr ||
      length == 0) {
    return 0;
  }

  size_t consumed = 0;
  while (consumed < length) {
    size_t stereo_samples = 0;

    if (has_carry_byte_ && consumed < length) {
      const int16_t raw_sample = static_cast<int16_t>(
          static_cast<uint16_t>(carry_byte_) |
          (static_cast<uint16_t>(data[consumed]) << 8));
      const int16_t sample = scale_sample(raw_sample);
      stereo_buffer_[stereo_samples * 2] = sample;
      stereo_buffer_[stereo_samples * 2 + 1] = sample;
      ++stereo_samples;
      ++consumed;
      reset_carry();
    }

    while (consumed + 1 < length &&
           stereo_samples < MONO_SAMPLES_PER_WRITE) {
      const int16_t raw_sample = static_cast<int16_t>(
          static_cast<uint16_t>(data[consumed]) |
          (static_cast<uint16_t>(data[consumed + 1]) << 8));
      const int16_t sample = scale_sample(raw_sample);
      stereo_buffer_[stereo_samples * 2] = sample;
      stereo_buffer_[stereo_samples * 2 + 1] = sample;
      ++stereo_samples;
      consumed += 2;
    }

    if (stereo_samples > 0) {
      const size_t stereo_bytes = stereo_samples * 2 * sizeof(int16_t);
      size_t bytes_written = 0;
      const esp_err_t write_result = i2s_write(
          I2S_NUM_0, stereo_buffer_, stereo_bytes, &bytes_written,
          portMAX_DELAY);
      if (write_result != ESP_OK || bytes_written != stereo_bytes) {
        Serial.println("I2S PCM write failed");
        break;
      }
    }

    if (consumed < length && length - consumed == 1) {
      carry_byte_ = data[consumed++];
      has_carry_byte_ = true;
    }
  }

  return consumed;
}

bool PcmPlayer::ready() const { return initialized_; }

bool PcmPlayer::playing() const { return playing_; }

void PcmPlayer::shutdown_driver() {
  i2s_driver_uninstall(I2S_NUM_0);
  initialized_ = false;
}

void PcmPlayer::reset_carry() {
  has_carry_byte_ = false;
  carry_byte_ = 0;
}

}  // namespace audio
}  // namespace mimi
