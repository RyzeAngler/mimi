#pragma once

#include <Arduino.h>

namespace mimi {
namespace debug {

// Serial telemetry is intentionally low frequency so it does not disturb the
// 20 ms sensor loop or the OLED animation.
constexpr bool ENABLE_MOTION_TELEMETRY = true;
constexpr uint32_t MOTION_TELEMETRY_INTERVAL_MS = 250;

}  // namespace debug
}  // namespace mimi
