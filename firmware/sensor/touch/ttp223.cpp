#include "ttp223.h"

namespace mimi {
namespace sensor {
namespace touch {

void Ttp223::begin(uint8_t signal_pin, bool active_high,
                   uint32_t debounce_ms) {
  signal_pin_ = signal_pin;
  active_high_ = active_high;
  debounce_ms_ = debounce_ms;
  pinMode(signal_pin_, INPUT);

  const bool electrical_high = digitalRead(signal_pin_) == HIGH;
  raw_state_ = active_high_ ? electrical_high : !electrical_high;
  stable_state_ = raw_state_;
  raw_changed_at_ms_ = millis();
  initialized_ = true;
}

TouchTransition Ttp223::update(uint32_t now_ms) {
  if (!initialized_) {
    return TouchTransition::None;
  }

  const bool electrical_high = digitalRead(signal_pin_) == HIGH;
  const bool current_raw = active_high_ ? electrical_high : !electrical_high;
  if (current_raw != raw_state_) {
    raw_state_ = current_raw;
    raw_changed_at_ms_ = now_ms;
  }

  if (raw_state_ == stable_state_ ||
      now_ms - raw_changed_at_ms_ < debounce_ms_) {
    return TouchTransition::None;
  }

  stable_state_ = raw_state_;
  return stable_state_ ? TouchTransition::Pressed
                       : TouchTransition::Released;
}

bool Ttp223::ready() const { return initialized_; }

bool Ttp223::touched() const { return stable_state_; }

uint8_t Ttp223::signal_pin() const { return signal_pin_; }

const char* touch_transition_name(TouchTransition transition) {
  switch (transition) {
    case TouchTransition::None:
      return "none";
    case TouchTransition::Pressed:
      return "pressed";
    case TouchTransition::Released:
      return "released";
  }
  return "unknown";
}

}  // namespace touch
}  // namespace sensor
}  // namespace mimi
