#include "mpu6050.h"

#include <math.h>

namespace mimi {
namespace sensor {
namespace motion {

namespace {
constexpr uint8_t kWhoAmIRegister = 0x75;
constexpr uint8_t kSampleRateDividerRegister = 0x19;
constexpr uint8_t kConfigRegister = 0x1A;
constexpr uint8_t kGyroConfigRegister = 0x1B;
constexpr uint8_t kAccelConfigRegister = 0x1C;
constexpr uint8_t kAccelOutputRegister = 0x3B;
constexpr uint8_t kPowerManagement1Register = 0x6B;
constexpr uint8_t kExpectedWhoAmI = 0x68;
constexpr uint8_t kOutputBytes = 14;
constexpr float kAccelScale = 16384.0f;  // +/-2 g
constexpr float kGyroScale = 131.0f;    // +/-250 degrees/second
}  // namespace

bool Mpu6050::begin(TwoWire& wire, uint8_t preferred_address) {
  wire_ = &wire;
  address_ = preferred_address;
  ready_ = false;

  if (!probe(address_)) {
    const uint8_t alternate = address_ == 0x68 ? 0x69 : 0x68;
    if (!probe(alternate)) {
      return false;
    }
    address_ = alternate;
  }

  if (!read_register(kWhoAmIRegister, who_am_i_)) {
    return false;
  }

  // MPU6050 modules normally return 0x68. Keep the ACK probe as the primary
  // test because compatible modules sometimes report a different identity.
  if (who_am_i_ != kExpectedWhoAmI) {
    return false;
  }

  const bool configured =
      write_register(kPowerManagement1Register, 0x00) &&
      write_register(kSampleRateDividerRegister, 9) &&  // 100 Hz output
      write_register(kConfigRegister, 0x03) &&          // DLPF ~44 Hz
      write_register(kGyroConfigRegister, 0x00) &&      // +/-250 dps
      write_register(kAccelConfigRegister, 0x00);       // +/-2 g

  if (!configured) {
    return false;
  }

  delay(50);
  ready_ = true;
  return true;
}

bool Mpu6050::read(Mpu6050Sample& sample) {
  if (!ready_ || wire_ == nullptr) {
    return false;
  }

  wire_->beginTransmission(address_);
  wire_->write(kAccelOutputRegister);
  if (wire_->endTransmission(false) != 0) {
    return false;
  }

  const size_t received =
      wire_->requestFrom(static_cast<uint8_t>(address_),
                         static_cast<size_t>(kOutputBytes), true);
  if (received != kOutputBytes) {
    return false;
  }

  uint8_t data[kOutputBytes];
  for (uint8_t i = 0; i < kOutputBytes; ++i) {
    data[i] = wire_->read();
  }

  sample.accel_x_raw = static_cast<int16_t>((data[0] << 8) | data[1]);
  sample.accel_y_raw = static_cast<int16_t>((data[2] << 8) | data[3]);
  sample.accel_z_raw = static_cast<int16_t>((data[4] << 8) | data[5]);
  sample.gyro_x_raw = static_cast<int16_t>((data[8] << 8) | data[9]);
  sample.gyro_y_raw = static_cast<int16_t>((data[10] << 8) | data[11]);
  sample.gyro_z_raw = static_cast<int16_t>((data[12] << 8) | data[13]);

  sample.accel_x_g = sample.accel_x_raw / kAccelScale;
  sample.accel_y_g = sample.accel_y_raw / kAccelScale;
  sample.accel_z_g = sample.accel_z_raw / kAccelScale;
  sample.gyro_x_dps = sample.gyro_x_raw / kGyroScale;
  sample.gyro_y_dps = sample.gyro_y_raw / kGyroScale;
  sample.gyro_z_dps = sample.gyro_z_raw / kGyroScale;
  return true;
}

bool Mpu6050::ready() const { return ready_; }

uint8_t Mpu6050::address() const { return address_; }

uint8_t Mpu6050::who_am_i() const { return who_am_i_; }

bool Mpu6050::probe(uint8_t address) {
  if (wire_ == nullptr) {
    return false;
  }

  wire_->beginTransmission(address);
  return wire_->endTransmission() == 0;
}

bool Mpu6050::write_register(uint8_t reg, uint8_t value) {
  if (wire_ == nullptr) {
    return false;
  }

  wire_->beginTransmission(address_);
  wire_->write(reg);
  wire_->write(value);
  return wire_->endTransmission() == 0;
}

bool Mpu6050::read_register(uint8_t reg, uint8_t& value) {
  if (wire_ == nullptr) {
    return false;
  }

  wire_->beginTransmission(address_);
  wire_->write(reg);
  if (wire_->endTransmission(false) != 0) {
    return false;
  }

  if (wire_->requestFrom(static_cast<uint8_t>(address_),
                         static_cast<size_t>(1), true) != 1) {
    return false;
  }

  value = wire_->read();
  return true;
}

}  // namespace motion
}  // namespace sensor
}  // namespace mimi
