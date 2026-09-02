#pragma once

#include <Arduino.h>

#include "expression/roboeyes/roboeyes_face.h"
#include "sensor/motion/motion_detector.h"

namespace mimi {
namespace behavior {

enum class BehaviorMode : uint8_t {
  Calm,
  Curious,
  Excited,
  Dizzy,
  Sleepy,
};

const char* behavior_mode_name(BehaviorMode mode);

enum class VisualState : uint8_t {
  Idle,
  Thinking,
  Speaking,
  Draining,
};

const char* visual_state_name(VisualState state);

class MotionExpressionController {
 public:
  void update(sensor::motion::MotionState state,
              const sensor::motion::MotionFeatures& features,
              uint32_t now_ms, expression::RoboEyesFace& face);
  void begin_thinking(uint32_t now_ms, expression::RoboEyesFace& face);
  void begin_speaking(sensor::motion::MotionState state,
                      const sensor::motion::MotionFeatures& features,
                      bool touch_event, uint32_t now_ms,
                      expression::RoboEyesFace& face);
  void begin_draining();
  void finish_reaction(const sensor::motion::MotionFeatures& features,
                       uint32_t now_ms, expression::RoboEyesFace& face);
  void cancel_reaction(const sensor::motion::MotionFeatures& features,
                       uint32_t now_ms, expression::RoboEyesFace& face);
  // Resolve the immediate semantic reaction for an event. Unlike mode(),
  // this does not wait for display-mode hysteresis or a previous idle sample.
  BehaviorMode reaction_mode(
      sensor::motion::MotionState state,
      const sensor::motion::MotionFeatures& features) const;
  BehaviorMode mode() const;
  VisualState visual_state() const;

 private:
  struct ModeScores {
    float calm = 0.0f;
    float curious = 0.0f;
    float excited = 0.0f;
    float dizzy = 0.0f;
    float sleepy = 0.0f;
  };

  ModeScores score_modes(sensor::motion::MotionState state,
                         const sensor::motion::MotionFeatures& features) const;
  BehaviorMode best_mode(const ModeScores& scores) const;
  float score_for_mode(BehaviorMode mode, const ModeScores& scores) const;
  void apply_mode(BehaviorMode mode, const sensor::motion::MotionFeatures& features,
                  uint32_t now_ms, expression::RoboEyesFace& face);
  void update_effects(const sensor::motion::MotionFeatures& features,
                      uint32_t now_ms, expression::RoboEyesFace& face);
  void apply_touch_reaction(expression::RoboEyesFace& face);
  void enter_idle(const sensor::motion::MotionFeatures& features,
                  uint32_t now_ms, bool randomize,
                  expression::RoboEyesFace& face);
  expression::Position gaze_from_tilt(
      const sensor::motion::MotionFeatures& features) const;

  bool initialized_ = false;
  BehaviorMode active_mode_ = BehaviorMode::Calm;
  BehaviorMode candidate_mode_ = BehaviorMode::Calm;
  uint32_t candidate_since_ms_ = 0;
  uint32_t mode_entered_ms_ = 0;
  uint32_t next_idle_blink_ms_ = 0;
  uint32_t next_effect_ms_ = 0;
  VisualState visual_state_ = VisualState::Idle;
};

}  // namespace behavior
}  // namespace mimi
