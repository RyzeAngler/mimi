#pragma once

#include <Arduino.h>

namespace mimi {
namespace pins {

// The board pinout diagram labels GPIO8 as SDA and GPIO9 as SCL.
// The separate schematic shows GPIO4/5, so GPIO4/5 remain the fallback
// profile if the physical board does not respond on the pinout profile.
constexpr int I2C_SDA = 8;
constexpr int I2C_SCL = 9;
constexpr int I2C_FALLBACK_SDA = 4;
constexpr int I2C_FALLBACK_SCL = 5;
constexpr uint32_t I2C_FREQUENCY_HZ = 100000;

constexpr int TOUCH_SIG = 10;
constexpr bool TOUCH_ACTIVE_HIGH = true;
constexpr uint32_t TOUCH_DEBOUNCE_MS = 50;
constexpr int MPU6050_INT = 3;
constexpr uint8_t MPU6050_ADDRESS = 0x68;
constexpr uint32_t MPU6050_READ_INTERVAL_MS = 20;

// Provisional I2S assignment. Confirm against the actual MAX98357A module.
constexpr int I2S_BCLK = 6;
constexpr int I2S_LRCLK = 7;
constexpr int I2S_DOUT = 21;

}  // namespace pins
}  // namespace mimi
