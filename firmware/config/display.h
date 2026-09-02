#pragma once

#include <Arduino.h>

namespace mimi {
namespace display {

constexpr int WIDTH = 128;
constexpr int HEIGHT = 64;
constexpr uint8_t DEFAULT_ADDRESS = 0x3C;
constexpr uint8_t ALTERNATE_ADDRESS = 0x3D;
constexpr uint8_t FRAME_RATE = 30;

}  // namespace display
}  // namespace mimi
