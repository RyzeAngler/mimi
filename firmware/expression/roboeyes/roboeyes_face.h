#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace mimi {
namespace expression {

enum class Mood : uint8_t {
  Default = 0,
  Tired = 1,
  Angry = 2,
  Happy = 3,
};

enum class Position : uint8_t {
  Center = 0,
  North = 1,
  NorthEast = 2,
  East = 3,
  SouthEast = 4,
  South = 5,
  SouthWest = 6,
  West = 7,
  NorthWest = 8,
};

enum class Effect : uint8_t {
  None = 0,
  Blink = 1,
  Confused = 2,
  Laugh = 3,
};

const char* mood_name(Mood mood);
const char* position_name(Position position);
const char* effect_name(Effect effect);

class RoboEyesFace {
 public:
  explicit RoboEyesFace(TwoWire& wire = Wire);
  ~RoboEyesFace();

  RoboEyesFace(const RoboEyesFace&) = delete;
  RoboEyesFace& operator=(const RoboEyesFace&) = delete;

  // The I2C bus must be initialized before calling begin().
  bool begin(uint8_t preferred_address);
  void update();

  void set_mood(Mood mood);
  void set_position(Position position);
  void blink();
  void anim_confused();
  void anim_laugh();
  void set_autoblinker(bool active, uint16_t interval_seconds,
                       uint16_t variation_seconds);
  void set_idle_mode(bool active, uint16_t interval_seconds,
                     uint16_t variation_seconds);
  void set_curiosity(bool enabled);
  void set_sweat(bool enabled);
  void set_h_flicker(bool enabled, uint8_t amplitude = 2);
  void set_v_flicker(bool enabled, uint8_t amplitude = 2);

  bool ready() const;
  uint8_t address() const;
  Mood mood() const;
  Position position() const;
  Effect last_effect() const;

 private:
  struct Impl;
  Impl* impl_;
};

}  // namespace expression
}  // namespace mimi
