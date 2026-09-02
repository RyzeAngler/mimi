#pragma once

#include <Arduino.h>

namespace mimi {
namespace sensor {
namespace touch {

enum class TouchTransition : uint8_t {
  None,
  Pressed,
  Released,
};

// Digital TTP223 touch modules normally drive SIG HIGH while touched.
// The driver debounces the raw signal and reports only stable transitions.
class Ttp223 {
 public:
  void begin(uint8_t signal_pin, bool active_high = true,
             uint32_t debounce_ms = 50);

  TouchTransition update(uint32_t now_ms);

  bool ready() const;
  bool touched() const;
  uint8_t signal_pin() const;

 private:
  uint8_t signal_pin_ = 0;
  bool active_high_ = true;
  uint32_t debounce_ms_ = 50;
  bool initialized_ = false;
  bool raw_state_ = false;
  bool stable_state_ = false;
  uint32_t raw_changed_at_ms_ = 0;
};

const char* touch_transition_name(TouchTransition transition);

}  // namespace touch
}  // namespace sensor
}  // namespace mimi
