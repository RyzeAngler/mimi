#include "motion_detector.h"

#include <math.h>

#include "config/motion.h"

namespace mimi {
namespace sensor {
namespace motion {

namespace {
constexpr float kRadiansToDegrees = 57.2957795f;
constexpr float kTiltThresholdDegrees = 20.0f;
constexpr float kShakeAccelDeviation = 0.30f;
constexpr float kShakeGyroThresholdDps = 180.0f;
constexpr uint32_t kShakeHoldMs = 500;
constexpr uint8_t kStableSamples = 3;
constexpr float kGravityFilterAlpha = 0.12f;
constexpr float kStillIntensityThreshold = 0.08f;
constexpr float kTiltNormalizationDegrees = 60.0f;

float clamp01(float value) {
  if (value < 0.0f) {
    return 0.0f;
  }
  if (value > 1.0f) {
    return 1.0f;
  }
  return value;
}
}  // namespace

MotionState MotionDetector::update(const Mpu6050Sample& sample,
                                    uint32_t now_ms) {
  const float accel_norm = sqrtf(
      sample.accel_x_g * sample.accel_x_g +
      sample.accel_y_g * sample.accel_y_g +
      sample.accel_z_g * sample.accel_z_g);
  const float gyro_norm = sqrtf(
      sample.gyro_x_dps * sample.gyro_x_dps +
      sample.gyro_y_dps * sample.gyro_y_dps +
      sample.gyro_z_dps * sample.gyro_z_dps);

  if (!initialized_) {
    gravity_x_g_ = sample.accel_x_g;
    gravity_y_g_ = sample.accel_y_g;
    gravity_z_g_ = sample.accel_z_g;
    still_since_ms_ = now_ms;
    state_since_ms_ = now_ms;
    initialized_ = true;
  } else {
    gravity_x_g_ = gravity_x_g_ * (1.0f - kGravityFilterAlpha) +
                   sample.accel_x_g * kGravityFilterAlpha;
    gravity_y_g_ = gravity_y_g_ * (1.0f - kGravityFilterAlpha) +
                   sample.accel_y_g * kGravityFilterAlpha;
    gravity_z_g_ = gravity_z_g_ * (1.0f - kGravityFilterAlpha) +
                   sample.accel_z_g * kGravityFilterAlpha;
  }

  const float dynamic_acceleration = fabsf(accel_norm - 1.0f);
  const float angular_activity = clamp01((gyro_norm - 8.0f) / 220.0f);
  const float linear_activity = clamp01((dynamic_acceleration - 0.03f) / 0.35f);
  const float motion_intensity = clamp01(
      angular_activity * 0.70f + linear_activity * 0.30f);
  const float stability = clamp01(1.0f - motion_intensity);

  const float raw_roll =
      atan2f(gravity_y_g_, gravity_z_g_) * kRadiansToDegrees;
  const float raw_pitch = atan2f(
      -gravity_x_g_, sqrtf(gravity_y_g_ * gravity_y_g_ +
                           gravity_z_g_ * gravity_z_g_)) *
                        kRadiansToDegrees;
  const float roll = raw_roll * mimi::motion_config::MPU6050_ROLL_SIGN;
  const float pitch = raw_pitch * mimi::motion_config::MPU6050_PITCH_SIGN;
  const float tilt_strength = clamp01(
      fmaxf(fabsf(roll), fabsf(pitch)) / kTiltNormalizationDegrees);

  if (motion_intensity < kStillIntensityThreshold) {
    if (still_since_ms_ == 0) {
      still_since_ms_ = now_ms;
    }
  } else {
    still_since_ms_ = now_ms;
  }

  if (motion_intensity >= kStillIntensityThreshold) {
    if (!motion_active_) {
      motion_active_ = true;
      motion_since_ms_ = now_ms;
      peak_angular_speed_dps_ = gyro_norm;
      peak_dynamic_acceleration_g_ = dynamic_acceleration;
    } else {
      peak_angular_speed_dps_ =
          fmaxf(peak_angular_speed_dps_, gyro_norm);
      peak_dynamic_acceleration_g_ =
          fmaxf(peak_dynamic_acceleration_g_, dynamic_acceleration);
    }
  } else {
    motion_active_ = false;
    motion_since_ms_ = now_ms;
    peak_angular_speed_dps_ = 0.0f;
    peak_dynamic_acceleration_g_ = 0.0f;
  }

  features_.roll_deg = roll;
  features_.pitch_deg = pitch;
  features_.acceleration_norm_g = accel_norm;
  features_.dynamic_acceleration_g = dynamic_acceleration;
  features_.angular_speed_dps = gyro_norm;
  features_.motion_intensity = motion_intensity;
  features_.stability = stability;
  features_.tilt_strength = tilt_strength;
  features_.still_duration_ms = now_ms - still_since_ms_;
  features_.peak_angular_speed_dps = peak_angular_speed_dps_;
  features_.peak_dynamic_acceleration_g = peak_dynamic_acceleration_g_;
  features_.motion_duration_ms =
      motion_active_ ? now_ms - motion_since_ms_ : 0;

  const MotionState classified = classify(sample, now_ms);
  const MotionState previous_state = stable_state_;

  if (classified != candidate_state_) {
    candidate_state_ = classified;
    candidate_count_ = 1;
  } else if (candidate_count_ < kStableSamples) {
    ++candidate_count_;
  }

  if (candidate_count_ >= kStableSamples) {
    stable_state_ = candidate_state_;
  }

  if (stable_state_ != previous_state) {
    state_since_ms_ = now_ms;
  }
  features_.state_duration_ms = now_ms - state_since_ms_;
  features_.confidence = classification_confidence(stable_state_);

  return stable_state_;
}

const MotionFeatures& MotionDetector::features() const { return features_; }

MotionState MotionDetector::classify(const Mpu6050Sample& sample,
                                     uint32_t now_ms) {
  const float accel_norm = sqrtf(
      sample.accel_x_g * sample.accel_x_g +
      sample.accel_y_g * sample.accel_y_g +
      sample.accel_z_g * sample.accel_z_g);
  const float gyro_norm = sqrtf(
      sample.gyro_x_dps * sample.gyro_x_dps +
      sample.gyro_y_dps * sample.gyro_y_dps +
      sample.gyro_z_dps * sample.gyro_z_dps);

  if (fabsf(accel_norm - 1.0f) > kShakeAccelDeviation ||
      gyro_norm > kShakeGyroThresholdDps) {
    shaking_hold_until_ms_ = now_ms + kShakeHoldMs;
  }

  if (static_cast<int32_t>(now_ms - shaking_hold_until_ms_) < 0) {
    return MotionState::Shaking;
  }

  const float roll = features_.roll_deg;
  const float pitch = features_.pitch_deg;

  if (fabsf(roll) < kTiltThresholdDegrees &&
      fabsf(pitch) < kTiltThresholdDegrees) {
    return MotionState::Level;
  }

  if (fabsf(roll) >= fabsf(pitch)) {
    return roll > 0 ? MotionState::TiltRight : MotionState::TiltLeft;
  }
  return pitch > 0 ? MotionState::TiltForward : MotionState::TiltBackward;
}

float MotionDetector::classification_confidence(MotionState state) const {
  const float dominant_tilt =
      fmaxf(fabsf(features_.roll_deg), fabsf(features_.pitch_deg));
  const float tilt_axis_balance = dominant_tilt /
      (fabsf(features_.roll_deg) + fabsf(features_.pitch_deg) + 0.01f);

  float confidence = 0.0f;
  switch (state) {
    case MotionState::Level:
      confidence =
          0.65f * (1.0f - clamp01(dominant_tilt / kTiltThresholdDegrees)) +
          0.35f * (1.0f - features_.motion_intensity);
      break;
    case MotionState::TiltLeft:
    case MotionState::TiltRight:
    case MotionState::TiltForward:
    case MotionState::TiltBackward:
      confidence =
          0.65f * clamp01((dominant_tilt - kTiltThresholdDegrees) /
                           (kTiltNormalizationDegrees -
                            kTiltThresholdDegrees)) +
          0.35f * clamp01(tilt_axis_balance);
      break;
    case MotionState::Shaking:
      confidence =
          0.50f * clamp01(features_.angular_speed_dps /
                           kShakeGyroThresholdDps) +
          0.50f * clamp01(features_.dynamic_acceleration_g /
                           kShakeAccelDeviation);
      break;
  }
  const float stability =
      clamp01(static_cast<float>(candidate_count_) / kStableSamples);
  return clamp01(0.70f * confidence + 0.30f * stability);
}

const char* motion_state_name(MotionState state) {
  switch (state) {
    case MotionState::Level:
      return "level";
    case MotionState::TiltLeft:
      return "tilt_left";
    case MotionState::TiltRight:
      return "tilt_right";
    case MotionState::TiltForward:
      return "tilt_forward";
    case MotionState::TiltBackward:
      return "tilt_backward";
    case MotionState::Shaking:
      return "shaking";
  }
  return "unknown";
}

}  // namespace motion
}  // namespace sensor
}  // namespace mimi
