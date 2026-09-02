#pragma once

#include <Arduino.h>

#include "sensor/motion/mpu6050/mpu6050.h"

namespace mimi {
namespace sensor {
namespace motion {

enum class MotionState : uint8_t {
  Level,
  TiltLeft,
  TiltRight,
  TiltForward,
  TiltBackward,
  Shaking,
};

// Continuous features derived from the raw IMU stream. These are deliberately
// separate from MotionState so behavior can react to intensity and stability
// instead of only to a discrete direction label.
struct MotionFeatures {
  float roll_deg = 0.0f;
  float pitch_deg = 0.0f;
  float acceleration_norm_g = 0.0f;
  float dynamic_acceleration_g = 0.0f;
  float angular_speed_dps = 0.0f;
  float motion_intensity = 0.0f;  // 0 = still, 1 = vigorous movement
  float stability = 1.0f;         // 1 = stable, 0 = unstable
  float tilt_strength = 0.0f;     // 0 = level, 1 = strong tilt
  float peak_angular_speed_dps = 0.0f;
  float peak_dynamic_acceleration_g = 0.0f;
  float confidence = 0.0f;        // confidence in the current state estimate
  uint32_t still_duration_ms = 0;
  uint32_t state_duration_ms = 0;
  uint32_t motion_duration_ms = 0;
};

class MotionDetector {
 public:
  MotionState update(const Mpu6050Sample& sample, uint32_t now_ms);
  const MotionFeatures& features() const;

 private:
  MotionState classify(const Mpu6050Sample& sample, uint32_t now_ms);
  float classification_confidence(MotionState state) const;

  MotionState stable_state_ = MotionState::Level;
  MotionState candidate_state_ = MotionState::Level;
  uint8_t candidate_count_ = 0;
  uint32_t shaking_hold_until_ms_ = 0;
  uint32_t still_since_ms_ = 0;
  uint32_t state_since_ms_ = 0;
  uint32_t motion_since_ms_ = 0;
  bool initialized_ = false;
  bool motion_active_ = false;
  float gravity_x_g_ = 0.0f;
  float gravity_y_g_ = 0.0f;
  float gravity_z_g_ = 1.0f;
  float peak_angular_speed_dps_ = 0.0f;
  float peak_dynamic_acceleration_g_ = 0.0f;
  MotionFeatures features_;
};

const char* motion_state_name(MotionState state);

}  // namespace motion
}  // namespace sensor
}  // namespace mimi
