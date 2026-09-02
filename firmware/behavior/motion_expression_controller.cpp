#include "motion_expression_controller.h"

#include <math.h>

namespace mimi {
namespace behavior {

using sensor::motion::MotionFeatures;
using sensor::motion::MotionState;

namespace {
constexpr float kTiltDeadZoneDegrees = 12.0f;
constexpr float kModeHysteresis = 0.12f;
constexpr uint32_t kModeTransitionDwellMs = 700;
constexpr uint32_t kMinimumModeHoldMs = 900;
constexpr uint32_t kExcitedTransitionDwellMs = 250;
constexpr uint32_t kDizzyTransitionDwellMs = 100;
constexpr uint32_t kUrgentMinimumModeHoldMs = 250;
constexpr uint32_t kCalmBlinkIntervalMs = 5000;
constexpr uint32_t kSleepyAfterMs = 90000;
constexpr uint32_t kSleepyRampMs = 30000;
constexpr uint32_t kLaughCooldownMs = 3500;
constexpr uint32_t kConfusedCooldownMs = 2200;

float clamp01(float value) {
  if (value < 0.0f) {
    return 0.0f;
  }
  if (value > 1.0f) {
    return 1.0f;
  }
  return value;
}

bool is_static_tilt(MotionState state) {
  return state == MotionState::TiltLeft ||
         state == MotionState::TiltRight ||
         state == MotionState::TiltForward ||
         state == MotionState::TiltBackward;
}
}  // namespace

void MotionExpressionController::update(
    MotionState state, const MotionFeatures& features, uint32_t now_ms,
    expression::RoboEyesFace& face) {
  if (visual_state_ != VisualState::Idle) {
    return;
  }

  const ModeScores scores = score_modes(state, features);
  const BehaviorMode desired_mode = best_mode(scores);

  if (!initialized_) {
    initialized_ = true;
    active_mode_ = desired_mode;
    candidate_mode_ = desired_mode;
    candidate_since_ms_ = now_ms;
    mode_entered_ms_ = now_ms;
    apply_mode(active_mode_, features, now_ms, face);
  } else {
    if (desired_mode != candidate_mode_) {
      candidate_mode_ = desired_mode;
      candidate_since_ms_ = now_ms;
    }

    const float desired_score = score_for_mode(desired_mode, scores);
    const float active_score = score_for_mode(active_mode_, scores);
    const bool candidate_is_stronger =
        desired_score >= active_score + kModeHysteresis;
    const uint32_t transition_dwell_ms =
        desired_mode == BehaviorMode::Dizzy
            ? kDizzyTransitionDwellMs
            : desired_mode == BehaviorMode::Excited
                  ? kExcitedTransitionDwellMs
                  : kModeTransitionDwellMs;
    const uint32_t minimum_hold_ms =
        desired_mode == BehaviorMode::Dizzy ||
                desired_mode == BehaviorMode::Excited
            ? kUrgentMinimumModeHoldMs
            : kMinimumModeHoldMs;
    const bool candidate_is_stable =
        now_ms - candidate_since_ms_ >= transition_dwell_ms;
    const bool minimum_hold_elapsed =
        now_ms - mode_entered_ms_ >= minimum_hold_ms;

    if (desired_mode != active_mode_ && candidate_is_stronger &&
        candidate_is_stable && minimum_hold_elapsed) {
      active_mode_ = desired_mode;
      mode_entered_ms_ = now_ms;
      apply_mode(active_mode_, features, now_ms, face);
    }
  }

  // The base gaze follows the filtered tilt continuously. RoboEyes performs
  // the pixel-level tweening, so this remains smooth even though the sensor
  // is sampled every 20 ms.
  if (active_mode_ != BehaviorMode::Sleepy) {
    const expression::Position gaze = gaze_from_tilt(features);
    if (face.position() != gaze) {
      face.set_position(gaze);
    }
  }

  update_effects(features, now_ms, face);
}

void MotionExpressionController::begin_thinking(
    uint32_t now_ms, expression::RoboEyesFace& face) {
  (void)now_ms;
  visual_state_ = VisualState::Thinking;

  // Thinking is a pre-speech acknowledgement. It tells the user that Mimi
  // accepted the event, but it is deliberately not the final reaction tied
  // to the spoken response.
  face.set_autoblinker(false, 0, 0);
  face.set_idle_mode(false, 0, 0);
  face.set_sweat(false);
  face.set_h_flicker(false);
  face.set_v_flicker(false);
  face.set_mood(expression::Mood::Default);
  face.set_curiosity(true);
  face.set_position(expression::Position::NorthWest);
}

void MotionExpressionController::begin_speaking(
    MotionState state, const MotionFeatures& features, bool touch_event,
    uint32_t now_ms, expression::RoboEyesFace& face) {
  visual_state_ = VisualState::Speaking;
  if (touch_event) {
    apply_touch_reaction(face);
    return;
  }

  const BehaviorMode reaction = reaction_mode(state, features);
  initialized_ = true;
  active_mode_ = reaction;
  candidate_mode_ = reaction;
  candidate_since_ms_ = now_ms;
  mode_entered_ms_ = now_ms;
  apply_mode(reaction, features, now_ms, face);
}

BehaviorMode MotionExpressionController::reaction_mode(
    MotionState state, const MotionFeatures& features) const {
  return best_mode(score_modes(state, features));
}

void MotionExpressionController::begin_draining() {
  if (visual_state_ == VisualState::Speaking) {
    visual_state_ = VisualState::Draining;
  }
}

void MotionExpressionController::finish_reaction(
    const MotionFeatures& features, uint32_t now_ms,
    expression::RoboEyesFace& face) {
  enter_idle(features, now_ms, true, face);
}

void MotionExpressionController::cancel_reaction(
    const MotionFeatures& features, uint32_t now_ms,
    expression::RoboEyesFace& face) {
  enter_idle(features, now_ms, false, face);
}

void MotionExpressionController::apply_touch_reaction(
    expression::RoboEyesFace& face) {

  // The touch reaction is committed only when its speech starts. Clear
  // motion-specific modifiers so a touch never leaves Mimi looking angry or
  // dizzy.
  face.set_autoblinker(false, 0, 0);
  face.set_idle_mode(false, 0, 0);
  face.set_sweat(false);
  face.set_h_flicker(false);
  face.set_v_flicker(false);
  face.set_mood(expression::Mood::Happy);
  face.set_curiosity(true);
  face.set_position(expression::Position::Center);
  face.anim_laugh();
}

void MotionExpressionController::enter_idle(
    const MotionFeatures& features, uint32_t now_ms,
    bool randomize, expression::RoboEyesFace& face) {
  visual_state_ = VisualState::Idle;
  initialized_ = true;
  const BehaviorMode idle_mode =
      randomize && random(100) >= 75 ? BehaviorMode::Curious
                                     : BehaviorMode::Calm;
  active_mode_ = idle_mode;
  candidate_mode_ = idle_mode;
  candidate_since_ms_ = now_ms;
  mode_entered_ms_ = now_ms;
  apply_mode(idle_mode, features, now_ms, face);
}

MotionExpressionController::ModeScores
MotionExpressionController::score_modes(
    MotionState state, const MotionFeatures& features) const {
  const float intensity = features.motion_intensity;
  const float stability = features.stability;
  const float tilt = features.tilt_strength;
  const float stillness =
      features.still_duration_ms <= kSleepyAfterMs
          ? 0.0f
          : clamp01(static_cast<float>(features.still_duration_ms -
                                        kSleepyAfterMs) /
                    static_cast<float>(kSleepyRampMs));
  const bool tilted = is_static_tilt(state);

  ModeScores scores;

  // Calm wins when the device is stable and close to level. A tilt reduces
  // calmness continuously instead of switching at one hard angle.
  scores.calm = clamp01(stability * (1.0f - 0.80f * tilt) +
                        (state == MotionState::Level ? 0.12f : 0.0f));
  scores.calm *= 1.0f - 0.45f * stillness;

  // Curiosity is strongest for a stable, intentional tilt. The state label
  // only adds a small prior; the continuous tilt and motion features do the
  // real work.
  scores.curious = clamp01(
      tilt * (1.15f - 0.55f * intensity) + (tilted ? 0.45f : 0.0f));

  // Excitement responds to angular speed and dynamic acceleration, but does
  // not steal the scene from the stronger dizzy score.
  scores.excited = clamp01(intensity * 1.25f +
                           (state == MotionState::TiltForward ||
                                    state == MotionState::TiltBackward
                                ? 0.08f
                                : 0.0f));

  // A violent or irregular movement is treated as dizzy. Shaking gets a hard
  // high score so it wins over the softer excited mode.
  scores.dizzy = state == MotionState::Shaking
                     ? 1.0f
                     : clamp01((intensity - 0.48f) / 0.42f);

  // After a long quiet period Mimi gradually becomes sleepy, rather than
  // jumping to tired as soon as the board stops moving.
  scores.sleepy = clamp01(stillness * 0.90f);
  return scores;
}

BehaviorMode MotionExpressionController::best_mode(
    const ModeScores& scores) const {
  BehaviorMode best = BehaviorMode::Calm;
  float best_score = scores.calm;

  if (scores.curious > best_score) {
    best = BehaviorMode::Curious;
    best_score = scores.curious;
  }
  if (scores.excited > best_score) {
    best = BehaviorMode::Excited;
    best_score = scores.excited;
  }
  if (scores.dizzy > best_score) {
    best = BehaviorMode::Dizzy;
    best_score = scores.dizzy;
  }
  if (scores.sleepy > best_score) {
    best = BehaviorMode::Sleepy;
  }
  return best;
}

float MotionExpressionController::score_for_mode(
    BehaviorMode mode, const ModeScores& scores) const {
  switch (mode) {
    case BehaviorMode::Calm:
      return scores.calm;
    case BehaviorMode::Curious:
      return scores.curious;
    case BehaviorMode::Excited:
      return scores.excited;
    case BehaviorMode::Dizzy:
      return scores.dizzy;
    case BehaviorMode::Sleepy:
      return scores.sleepy;
  }
  return 0.0f;
}

void MotionExpressionController::apply_mode(
    BehaviorMode mode, const MotionFeatures& features, uint32_t now_ms,
    expression::RoboEyesFace& face) {
  // Reset transient visual modifiers before applying the new behavior.
  face.set_autoblinker(false, 0, 0);
  face.set_idle_mode(false, 0, 0);
  face.set_sweat(false);
  face.set_h_flicker(false);
  face.set_v_flicker(false);

  switch (mode) {
    case BehaviorMode::Calm:
      face.set_mood(expression::Mood::Happy);
      face.set_curiosity(true);
      face.set_position(gaze_from_tilt(features));
      // Keep the default product behavior: a deliberate friendly blink every
      // 5 seconds, while idle mode adds occasional natural eye movement.
      face.set_idle_mode(true, 5, 2);
      next_idle_blink_ms_ = now_ms + kCalmBlinkIntervalMs;
      next_effect_ms_ = now_ms;
      break;

    case BehaviorMode::Curious:
      face.set_mood(expression::Mood::Default);
      face.set_curiosity(true);
      face.set_position(gaze_from_tilt(features));
      face.set_autoblinker(true, 5, 2);
      next_effect_ms_ = now_ms + 5000;
      break;

    case BehaviorMode::Excited:
      face.set_mood(expression::Mood::Happy);
      face.set_curiosity(true);
      face.set_position(gaze_from_tilt(features));
      face.anim_laugh();
      next_effect_ms_ = now_ms + kLaughCooldownMs;
      break;

    case BehaviorMode::Dizzy:
      face.set_mood(expression::Mood::Angry);
      face.set_curiosity(false);
      face.set_position(expression::Position::Center);
      face.set_sweat(true);
      face.set_h_flicker(true, 2);
      face.set_v_flicker(true, 1);
      face.anim_confused();
      next_effect_ms_ = now_ms + kConfusedCooldownMs;
      break;

    case BehaviorMode::Sleepy:
      face.set_mood(expression::Mood::Tired);
      face.set_curiosity(false);
      face.set_position(expression::Position::South);
      face.set_autoblinker(true, 10, 4);
      next_effect_ms_ = now_ms + 12000;
      break;
  }
}

void MotionExpressionController::update_effects(
    const MotionFeatures& features, uint32_t now_ms,
    expression::RoboEyesFace& face) {
  switch (active_mode_) {
    case BehaviorMode::Calm:
      if (static_cast<int32_t>(now_ms - next_idle_blink_ms_) >= 0) {
        face.set_mood(expression::Mood::Happy);
        face.blink();
        next_idle_blink_ms_ = now_ms + kCalmBlinkIntervalMs;
      }
      break;

    case BehaviorMode::Excited:
      if (features.motion_intensity > 0.20f &&
          static_cast<int32_t>(now_ms - next_effect_ms_) >= 0) {
        face.anim_laugh();
        next_effect_ms_ = now_ms + kLaughCooldownMs;
      }
      break;

    case BehaviorMode::Dizzy:
      if (static_cast<int32_t>(now_ms - next_effect_ms_) >= 0) {
        face.anim_confused();
        next_effect_ms_ = now_ms + kConfusedCooldownMs;
      }
      break;

    case BehaviorMode::Curious:
    case BehaviorMode::Sleepy:
      break;
  }
}

expression::Position MotionExpressionController::gaze_from_tilt(
    const MotionFeatures& features) const {
  const bool north = features.pitch_deg < -kTiltDeadZoneDegrees;
  const bool south = features.pitch_deg > kTiltDeadZoneDegrees;
  const bool east = features.roll_deg > kTiltDeadZoneDegrees;
  const bool west = features.roll_deg < -kTiltDeadZoneDegrees;

  if (north && east) {
    return expression::Position::NorthEast;
  }
  if (south && east) {
    return expression::Position::SouthEast;
  }
  if (south && west) {
    return expression::Position::SouthWest;
  }
  if (north && west) {
    return expression::Position::NorthWest;
  }
  if (north) {
    return expression::Position::North;
  }
  if (east) {
    return expression::Position::East;
  }
  if (south) {
    return expression::Position::South;
  }
  if (west) {
    return expression::Position::West;
  }
  return expression::Position::Center;
}

BehaviorMode MotionExpressionController::mode() const { return active_mode_; }

VisualState MotionExpressionController::visual_state() const {
  return visual_state_;
}

const char* behavior_mode_name(BehaviorMode mode) {
  switch (mode) {
    case BehaviorMode::Calm:
      return "calm";
    case BehaviorMode::Curious:
      return "curious";
    case BehaviorMode::Excited:
      return "excited";
    case BehaviorMode::Dizzy:
      return "dizzy";
    case BehaviorMode::Sleepy:
      return "sleepy";
  }
  return "unknown";
}

const char* visual_state_name(VisualState state) {
  switch (state) {
    case VisualState::Idle:
      return "idle";
    case VisualState::Thinking:
      return "thinking";
    case VisualState::Speaking:
      return "speaking";
    case VisualState::Draining:
      return "draining";
  }
  return "unknown";
}

}  // namespace behavior
}  // namespace mimi
