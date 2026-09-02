#include "roboeyes_face.h"

#include <Adafruit_SSD1306.h>

// RoboEyes currently defines display colors and short expression names in its
// header. Keep the dependency private to this translation unit so its globals
// cannot leak into the rest of Mimi or be defined in multiple object files.
#ifdef DEFAULT
#undef DEFAULT
#endif
#include <FluxGarage_RoboEyes.h>
#ifdef DEFAULT
#undef DEFAULT
#endif
#ifdef TIRED
#undef TIRED
#endif
#ifdef ANGRY
#undef ANGRY
#endif
#ifdef HAPPY
#undef HAPPY
#endif
#ifdef ON
#undef ON
#endif
#ifdef OFF
#undef OFF
#endif
#ifdef N
#undef N
#endif
#ifdef NE
#undef NE
#endif
#ifdef E
#undef E
#endif
#ifdef SE
#undef SE
#endif
#ifdef S
#undef S
#endif
#ifdef SW
#undef SW
#endif
#ifdef W
#undef W
#endif
#ifdef NW
#undef NW
#endif

#include "config/display.h"

namespace mimi {
namespace expression {

namespace {
constexpr unsigned char kDefault = 0;
constexpr unsigned char kTired = 1;
constexpr unsigned char kAngry = 2;
constexpr unsigned char kHappy = 3;
constexpr unsigned char kCenter = 0;
constexpr unsigned char kNorth = 1;
constexpr unsigned char kNorthEast = 2;
constexpr unsigned char kEast = 3;
constexpr unsigned char kSouthEast = 4;
constexpr unsigned char kSouth = 5;
constexpr unsigned char kSouthWest = 6;
constexpr unsigned char kWest = 7;
constexpr unsigned char kNorthWest = 8;
}  // namespace

struct RoboEyesFace::Impl {
  explicit Impl(TwoWire& wire)
      : wire(wire),
        display(display::WIDTH, display::HEIGHT, &wire, -1),
        eyes(display) {}

  uint8_t detect_address(uint8_t preferred_address) {
    const uint8_t candidates[] = {
        preferred_address,
        preferred_address == display::DEFAULT_ADDRESS
            ? display::ALTERNATE_ADDRESS
            : display::DEFAULT_ADDRESS,
    };

    for (uint8_t candidate : candidates) {
      wire.beginTransmission(candidate);
      if (wire.endTransmission() == 0) {
        return candidate;
      }
    }

    return 0;
  }

  TwoWire& wire;
  Adafruit_SSD1306 display;
  RoboEyes<Adafruit_SSD1306> eyes;
  bool ready = false;
  uint8_t address = 0;
  Mood mood = Mood::Default;
  Position position = Position::Center;
  Effect last_effect = Effect::None;
};

RoboEyesFace::RoboEyesFace(TwoWire& wire) : impl_(new Impl(wire)) {}

RoboEyesFace::~RoboEyesFace() { delete impl_; }

bool RoboEyesFace::begin(uint8_t preferred_address) {
  impl_->address = impl_->detect_address(preferred_address);
  if (impl_->address == 0 ||
      !impl_->display.begin(SSD1306_SWITCHCAPVCC, impl_->address)) {
    impl_->ready = false;
    return false;
  }

  impl_->display.clearDisplay();
  impl_->display.display();

  impl_->eyes.begin(display::WIDTH, display::HEIGHT,
                    display::FRAME_RATE);
  impl_->eyes.setDisplayColors(SSD1306_BLACK, SSD1306_WHITE);
  impl_->eyes.setWidth(34, 34);
  impl_->eyes.setHeight(34, 34);
  impl_->eyes.setBorderradius(8, 8);
  impl_->eyes.setSpacebetween(10);
  impl_->eyes.setPosition(kCenter);
  impl_->eyes.setMood(kDefault);
  impl_->eyes.setCuriosity(true);
  impl_->eyes.setAutoblinker(false, 0, 0);
  impl_->eyes.setIdleMode(false, 0, 0);
  impl_->eyes.open();

  impl_->mood = Mood::Happy;
  impl_->position = Position::Center;
  impl_->last_effect = Effect::None;
  impl_->ready = true;
  return true;
}

void RoboEyesFace::update() {
  if (impl_->ready) {
    impl_->eyes.update();
  }
}

void RoboEyesFace::set_mood(Mood mood) {
  impl_->mood = mood;
  if (impl_->ready) {
    impl_->eyes.setMood(static_cast<unsigned char>(mood));
  }
}

void RoboEyesFace::set_position(Position position) {
  impl_->position = position;
  if (impl_->ready) {
    impl_->eyes.setPosition(static_cast<unsigned char>(position));
  }
}

void RoboEyesFace::blink() {
  impl_->last_effect = Effect::Blink;
  if (impl_->ready) {
    impl_->eyes.blink();
  }
}

void RoboEyesFace::anim_confused() {
  impl_->last_effect = Effect::Confused;
  if (impl_->ready) {
    impl_->eyes.anim_confused();
  }
}

void RoboEyesFace::anim_laugh() {
  impl_->last_effect = Effect::Laugh;
  if (impl_->ready) {
    impl_->eyes.anim_laugh();
  }
}

void RoboEyesFace::set_autoblinker(bool active, uint16_t interval_seconds,
                                   uint16_t variation_seconds) {
  if (impl_->ready) {
    impl_->eyes.setAutoblinker(active, interval_seconds, variation_seconds);
  }
}

void RoboEyesFace::set_idle_mode(bool active, uint16_t interval_seconds,
                                 uint16_t variation_seconds) {
  if (impl_->ready) {
    impl_->eyes.setIdleMode(active, interval_seconds, variation_seconds);
  }
}

void RoboEyesFace::set_curiosity(bool enabled) {
  if (impl_->ready) {
    impl_->eyes.setCuriosity(enabled);
  }
}

void RoboEyesFace::set_sweat(bool enabled) {
  if (impl_->ready) {
    impl_->eyes.setSweat(enabled);
  }
}

void RoboEyesFace::set_h_flicker(bool enabled, uint8_t amplitude) {
  if (impl_->ready) {
    impl_->eyes.setHFlicker(enabled, amplitude);
  }
}

void RoboEyesFace::set_v_flicker(bool enabled, uint8_t amplitude) {
  if (impl_->ready) {
    impl_->eyes.setVFlicker(enabled, amplitude);
  }
}

bool RoboEyesFace::ready() const { return impl_->ready; }

uint8_t RoboEyesFace::address() const { return impl_->address; }

Mood RoboEyesFace::mood() const { return impl_->mood; }

Position RoboEyesFace::position() const { return impl_->position; }

Effect RoboEyesFace::last_effect() const { return impl_->last_effect; }

const char* mood_name(Mood mood) {
  switch (mood) {
    case Mood::Default:
      return "default";
    case Mood::Tired:
      return "tired";
    case Mood::Angry:
      return "angry";
    case Mood::Happy:
      return "happy";
  }
  return "unknown";
}

const char* position_name(Position position) {
  switch (position) {
    case Position::Center:
      return "center";
    case Position::North:
      return "north";
    case Position::NorthEast:
      return "north_east";
    case Position::East:
      return "east";
    case Position::SouthEast:
      return "south_east";
    case Position::South:
      return "south";
    case Position::SouthWest:
      return "south_west";
    case Position::West:
      return "west";
    case Position::NorthWest:
      return "north_west";
  }
  return "unknown";
}

const char* effect_name(Effect effect) {
  switch (effect) {
    case Effect::None:
      return "none";
    case Effect::Blink:
      return "blink";
    case Effect::Confused:
      return "confused";
    case Effect::Laugh:
      return "laugh";
  }
  return "unknown";
}

}  // namespace expression
}  // namespace mimi
