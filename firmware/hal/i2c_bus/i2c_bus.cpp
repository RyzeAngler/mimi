#include "i2c_bus.h"

namespace mimi {
namespace hal {

I2cBus::I2cBus(TwoWire& wire) : wire_(wire) {}

void I2cBus::begin(int sda_pin, int scl_pin, uint32_t frequency_hz) {
  wire_.begin(sda_pin, scl_pin, frequency_hz);
}

void I2cBus::scan(Stream& output, int sda_pin, int scl_pin) {
  output.println("I2C scan started");
  output.print("SDA=");
  output.print(sda_pin);
  output.print(", SCL=");
  output.println(scl_pin);

  uint8_t device_count = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    wire_.beginTransmission(address);
    const uint8_t error = wire_.endTransmission();

    if (error == 0) {
      output.print("I2C device found at 0x");
      if (address < 0x10) {
        output.print('0');
      }
      output.println(address, HEX);
      ++device_count;
    }
  }

  if (device_count == 0) {
    output.println("No I2C devices found");
  } else {
    output.print("I2C devices found: ");
    output.println(device_count);
  }
  output.println("I2C scan finished");
}

TwoWire& I2cBus::wire() { return wire_; }

}  // namespace hal
}  // namespace mimi
