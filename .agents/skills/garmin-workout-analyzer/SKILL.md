---
name: garmin-workout-analyzer
description: >-
  Use this skill to fetch, analyze, and coach on Garmin Connect activities and health metrics.
  Trigger when the user asks about workouts, running/cycling training analysis, recovery status,
  HRV, sleep, training effect, heart rate zones, or personalized coaching recommendations from Garmin.
---

# Garmin Workout & Health Analysis Skill

This skill guides the AI in querying the Garmin Personal API via `garmin-personal-mcp` to retrieve athletic activities and physiological telemetry, analyze training stress, and provide actionable sports science insights.

## Available MCP Tools Overview

When `garmin-personal-mcp` is active and authenticated, use the following tools:
- `garmin_search_activities`: Find recent activities by date range (`start_date`, `end_date`), activity type (e.g. running, cycling, swimming), and limit.
- `garmin_get_activity`: Get detailed metrics for a specific activity by its ID (pace, cadence, heart rate, elevation, training effect, laps).
- `garmin_download_activity`: Download the raw `.FIT` or original activity file if deep telemetry parsing is required.
- `garmin_get_day` / `garmin_get_daily_summary`: High-level daily summary including steps, calories, active minutes, and resting heart rate.
- `garmin_get_hrv` / `garmin_get_hrv_summaries`: Heart Rate Variability status (7-day baseline, overnight average, balanced vs unbalanced).
- `garmin_get_sleep` / `garmin_get_sleep_summaries`: Sleep stages (deep, light, REM, awake), sleep score, restlessness.
- `garmin_get_body_battery`: Energy reserve monitoring throughout the day.
- `garmin_get_heart_rate_zones`: User's configured HR zones (Zone 1 Recovery through Zone 5 Maximum).
- `garmin_get_fitness_age`: Garmin calculated fitness age and VO2 max insights.

## Analysis Workflows

### 1. Activity & Workout Breakdown
When the user asks to review a specific session or recent workout:
1. Search activities using `garmin_search_activities` to identify the relevant `activityId`.
2. Inspect details using `garmin_get_activity(activityId=...)`.
3. Analyze:
   - **Pacing & Consistency:** Splits stability, negative/positive split pacing.
   - **Heart Rate Distribution:** Time in Zone 2 (aerobic base) vs Zone 4/5 (threshold/anaerobic).
   - **Cadence & Biomechanics:** Running cadence (optimal ~170-185 spm) or cycling cadence.
   - **Training Effect (TE):** Aerobic and Anaerobic Training Effect scores (0.0 to 5.0).

### 2. Readiness & Recovery Analysis
Before prescribing high-intensity workouts or diagnosing fatigue:
1. Fetch overnight HRV: `garmin_get_hrv` (compare overnight average to baseline).
2. Fetch Sleep Score & Rest: `garmin_get_sleep`.
3. Inspect Body Battery drain & recharge: `garmin_get_body_battery`.
4. Synthesis:
   - If HRV is suppressed (< baseline) or Sleep Score < 65: Recommend active recovery (Zone 1) or complete rest.
   - If HRV is balanced and sleep is restorative (> 80): Athlete is primed for key workouts (intervals, tempo, long runs).

### 3. Coaching Recommendations
- Apply sports science principles (e.g., 80/20 polarized training: 80% low intensity Zone 1-2, 20% high intensity).
- Provide constructive feedback: highlight what went well, identify pacing fade or cardiac drift, and suggest adjustments for the upcoming training days.
