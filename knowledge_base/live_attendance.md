# Live Attendance

## What it does
Shows real-time indicators of which students are active, away, offline, or requesting entry, updating instantly via WebSockets.

## Why it exists
It helps teachers detect when a student is disengaged, has disconnected, or has minimized their browser window.

## When it should be used
Visible on the teacher dashboard roster during active classes.

## How to use it
1. Open the Roster panel on the dashboard.
2. Observe status indicator lights next to student names (Green = Active, Orange = Away, Red = Offline).
3. Click 'Refresh Roster' to manually force a status update if needed.

## Best practices
Keep an eye on the away count; if it rises, prompt the class with an interactive task to capture their attention.

## Common mistakes
Assuming a student is cutting class because their status turns Red briefly due to network latency.

## Troubleshooting steps
If student status lights are not changing, check if the WebSocket channel is active.

## Related features
Attendance Tracking, Classroom Controls
