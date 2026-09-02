#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace mimi {
namespace sensor {
namespace motion {

struct Mpu6050Sample {
  int16_t accel_x_raw = 0;
  int16_t accel_y_raw = 0;
  int16_t accel_z_raw = 0;
  int16_t gyro_x_raw = 0;
  int16_t gyro_y_raw = 0;
  int16_t gyro_z_raw = 0;

  float accel_x_g = 0.0f;
  float accel_y_g = 0.0f;
  float accel_z_g = 0.0f;
  float gyro_x_dps = 0.0f;
  float gyro_y_dps = 0.0f;
  float gyro_z_dps = 0.0f;
};

class Mpu6050 {
 public:
  Mpu6050() = default;

  bool begin(TwoWire& wire, uint8_t preferred_address = 0x68);
  bool read(Mpu6050Sample& sample);

  bool ready() const;
  uint8_t address() const;
  uint8_t who_am_i() const;

 private:
  bool probe(uint8_t address);
  bool write_register(uint8_t reg, uint8_t value);
  bool read_register(uint8_t reg, uint8_t& value);

  TwoWire* wire_ = nullptr;
  uint8_t address_ = 0;
  uint8_t who_am_i_ = 0;
  bool ready_ = false;
};

}  // namespace motion
}  // namespace sensor
}  // namespace mimi
