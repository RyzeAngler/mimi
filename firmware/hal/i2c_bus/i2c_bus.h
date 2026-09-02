#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace mimi {
namespace hal {

class I2cBus {
 public:
  explicit I2cBus(TwoWire& wire = Wire);

  void begin(int sda_pin, int scl_pin, uint32_t frequency_hz);
  void scan(Stream& output, int sda_pin, int scl_pin);

  TwoWire& wire();

 private:
  TwoWire& wire_;
};

}  // namespace hal
}  // namespace mimi
