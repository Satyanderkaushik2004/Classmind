# 🏗️ Attendance Dashboard - Architecture & Data Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     BROWSER (Frontend)                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          SmartAttendancePage Component                   │  │
│  │                                                          │  │
│  │  State:                                                  │  │
│  │  • att (attendance data)                                │  │
│  │  • isLoading                                            │  │
│  │  • fetchError                                           │  │
│  │  • retryCount                                           │  │
│  │                                                          │  │
│  │  Refs:                                                   │  │
│  │  • pollIntervalRef (polling timer)                      │  │
│  │  • fetchRetryRef (retry timer)                          │  │
│  │  • prevPresentRef (for toast notifications)             │  │
│  │  • prevExitedRef (for exit tracking)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                         ↓ ↑                                      │
│              ┌──────────┴─┴──────────┐                          │
│              │                       │                          │
│         Polling                  WebSocket                      │
│         (Every 2-15s)           (Real-time)                    │
│              │                       │                          │
└──────────────┼───────────────────────┼──────────────────────────┘
               │                       │
               ↓                       ↓
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (Python/FastAPI)                     │
│                                                                  │
│  ┌───────────────────────┐         ┌────────────────────────┐  │
│  │  REST Endpoint        │         │  WebSocket Handler     │  │
│  │  GET /api/session/    │         │  /ws/teacher/session/  │  │
│  │     {code}/attendance │         │                        │  │
│  │                       │         │  broadcast_attendance()│  │
│  │  compute_attendance_  │         │                        │  │
│  │  summary(s)           │         └────────────────────────┘  │
│  └───────────────────────┘                                      │
│              ↓                       ↑                           │
│              │                       │                           │
│              └───────────┬───────────┘                           │
│                          ↓                                       │
│           ┌──────────────────────────┐                          │
│           │   Session Data Store     │                          │
│           │                          │                          │
│           │  • Attendance Records    │                          │
│           │  • Student Status        │                          │
│           │  • Join/Leave Times      │                          │
│           │  • Attendance State      │                          │
│           │  • Min Duration          │                          │
│           └──────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Sequence

### 1️⃣ Initial Load
```
Page Open
    ↓
SmartAttendancePage mounts
    ↓
useEffect triggered
    ↓
fetchAttendanceData() called immediately (no delay!)
    ↓
GET /api/session/{code}/attendance
    ↓
compute_attendance_summary(session)
    ↓
JSON Response with real data
    ↓
validateAttendanceData(response)
    ↓
setAtt(validated) → State Updated
    ↓
UI Renders with REAL DATA
```

### 2️⃣ Polling Updates (During Active Session)
```
Every 2 seconds (when active):
    ↓
fetchAttendanceData()
    ↓
GET /api/session/{code}/attendance
    ↓
New attendance summary
    ↓
Validate data
    ↓
setAtt(validated) → State Updated
    ↓
Counter Cards Update ✓
Progress Ring Updates ✓
Student List Updates ✓
```

### 3️⃣ Real-Time WebSocket Updates (Instant)
```
Teacher Action (approve student, etc.)
    ↓
Backend processes change
    ↓
broadcast_attendance(session) called
    ↓
ws_teacher(session, {
  "type": "attendance_update",
  "attendance": compute_attendance_summary(s)
})
    ↓
Frontend receives WebSocket message
    ↓
window.__attUpdate(msg.attendance) called
    ↓
validateAttendanceData(data)
    ↓
setAtt(validated) → State Updated
    ↓
UI Updates IMMEDIATELY (<100ms)
Toast Notification Appears
```

## Counter Cards Data Mapping

```
Backend Response                Frontend Display
─────────────────────          ─────────────────
{
  "total": 45        ────→    Total Enrolled: 45
  "present": 38      ────→    Present: 38
  "exited": 2        ────→    Exited Early: 2
  "revoked": 1       ────→    Revoked: 1
  "late": 4          ────→    Late Joiners: 4
  "percentage": 84   ────→    Attendance %: 84%
}
```

## Real-Time Indicators

```
┌─────────────────────────────────────┐
│  Counter Card UI                    │
│                                     │
│  🟢 (pulse dot)  ← Active indicator │
│  Value: 38                          │
│  Label: Present                     │
│                                     │
│  Last update: 14:32:15             │ ← Tooltip
└─────────────────────────────────────┘
```

## Error Handling Flow

```
fetchAttendanceData()
    ↓
    ├─ Success ✅
    │   ↓
    │   updateState()
    │   displayData()
    │   
    ├─ Error ❌
    │   ↓
    │   Retry? (Max 3 times)
    │   ├─ Exponential backoff: 1s, 2s, 4s
    │   ├─ Show error banner to user
    │   ├─ Retry count display
    │   └─ Continue polling anyway
    │   
    └─ Max Retries Reached
        ↓
        Stop retrying
        Continue polling on next cycle
        Show persistent error banner
```

## Polling Strategy

```
Session State → Polling Interval → Reason
──────────────────────────────────────────
Active        → 2 seconds        → Real-time tracking
Paused        → 2 seconds        → Still monitoring
Inactive      → 10 seconds       → Background mode
Ended         → 5 seconds        → Final data important
Locked        → 15 seconds       → No changes expected
```

## State Update Triggers

```
┌─────────────────────────────────────────┐
│         setAtt(validated)               │
├─────────────────────────────────────────┤
│                                         │
│  Triggered by:                          │
│  1. Initial fetch (immediately)         │
│  2. Polling timer (every 2-15s)        │
│  3. WebSocket message (instant)         │
│                                         │
│  What Updates:                          │
│  • Counter cards ← New numbers          │
│  • Progress ring ← New percentage       │
│  • Student list ← New records           │
│  • Timestamp ← Last update time         │
│                                         │
└─────────────────────────────────────────┘
```

## Toast Notification Triggers

```
Event                           Toast Message
────────────────────────────────────────────
att.present increases  ───→    ✅ N student(s) joined
att.exited increases   ───→    ⏱ Student marked as exited early
```

## Validation Pipeline

```
Raw API Response
    ↓
validateAttendanceData()
    ├─ Check: data is object ✓
    ├─ Check: all fields present ✓
    ├─ Check: numeric values non-negative ✓
    ├─ Check: percentage 0-100 ✓
    ├─ Verify: (present / total) * 100 = percentage ✓
    ├─ Check: records properly structured ✓
    │
    ├─ ✅ All valid → Return validated object
    │   ↓
    │   setAtt(validated)
    │
    └─ ❌ Invalid → Log warning, return null
        ↓
        Don't update state
```

## Ref Management

```
Refs (persist across renders)

prevPresentRef
├─ Stores previous present count
├─ Used to detect new joins
└─ Triggers toast notification

prevExitedRef  
├─ Stores previous exited count
├─ Used to detect new exits
└─ Triggers exit toast

pollIntervalRef
├─ Stores current polling interval ID
├─ Cleaned up on state/unmount changes
└─ Allows stopping/restarting polling

fetchRetryRef
├─ Stores retry timer ID
├─ Cleaned up on successful fetch
└─ Allows canceling pending retry
```

## Browser Console Logging

```
Page Load:
  [ATTENDANCE] Triggering initial fetch for session: ABC123
  [ATTENDANCE] Fetching data from /api/session/ABC123/attendance
  [ATTENDANCE] Data validated and setting state: {...}
  [ATTENDANCE] Setting up polling with interval: 2000ms for state: active
  [ATTENDANCE] ✅ Fetch successful: {...}

During Active Session (every 2s):
  [ATTENDANCE] Polling tick: 14:32:45
  [ATTENDANCE] Fetching data from /api/session/ABC123/attendance
  [ATTENDANCE] Data validated and setting state: {...}
  [ATTENDANCE] ✅ Fetch successful: {...}

On Student Join (WebSocket):
  [ATTENDANCE] 🔔 WebSocket LIVE update received: {...}
  [ATTENDANCE] ✅ WebSocket update validated, applying to state
  [ATTENDANCE] 🎯 WebSocket update applied successfully

On Error:
  [ATTENDANCE] ❌ Fetch error: Network error
  [ATTENDANCE] Scheduling retry in 1000ms (attempt 1/3)
```

## Cleanup & Unmount

```
Component Unmount
    ↓
useEffect cleanup runs
    ├─ clearInterval(pollIntervalRef.current)
    ├─ clearTimeout(fetchRetryRef.current)
    └─ window.__attUpdate = null
    ↓
All listeners removed
Timers stopped
Memory freed
```

## Performance Optimizations

```
✅ Implemented:

1. Immediate Initial Fetch
   └─ No 100ms delay
   └─ Data visible instantly

2. Adaptive Polling
   └─ Faster when active (2s vs 5s)
   └─ Slower when locked (15s)
   └─ Saves bandwidth

3. Data Persistence
   └─ Retry uses last known data
   └─ Don't lose state on error

4. Efficient Updates
   └─ Only update if data changed
   └─ Don't update if total still 0

5. Cleanup Management
   └─ Proper interval/timeout cleanup
   └─ No memory leaks
   └─ Smooth component lifecycle
```

## Integration Points

```
TeacherShell Component
    ↓
    ├─ Manages WebSocket connection
    ├─ Receives attendance_update messages
    ├─ Calls window.__attUpdate(data)
    ↓
SmartAttendancePage Component
    ↓
    ├─ Displays data in UI
    ├─ Manages polling
    ├─ Listens for WebSocket updates
    └─ Shows real-time status

Session Store (Backend)
    ↓
    ├─ Stores attendance records
    ├─ Computes attendance summary
    └─ Broadcasts updates to teachers
```

## Key Features Summary

```
┌─────────────────────────────────────────────────────┐
│  ✅ Real-Time Data                                  │
├─────────────────────────────────────────────────────┤
│  • Immediate initial fetch (0ms delay)              │
│  • Polling every 2s when active                     │
│  • WebSocket for instant updates                    │
│  • Error recovery with exponential backoff          │
├─────────────────────────────────────────────────────┤
│  ✅ Live Visualizations                             │
├─────────────────────────────────────────────────────┤
│  • Counter cards with pulse animation               │
│  • Progress ring with smooth updates                │
│  • Student list with real-time status               │
│  • Color-coded status indicators                    │
├─────────────────────────────────────────────────────┤
│  ✅ User Feedback                                   │
├─────────────────────────────────────────────────────┤
│  • Toast notifications for joins/exits              │
│  • Error banner with retry attempts                 │
│  • Last updated timestamp                           │
│  • Loading states                                   │
├─────────────────────────────────────────────────────┤
│  ✅ Robustness                                      │
├─────────────────────────────────────────────────────┤
│  • Data validation on all inputs                    │
│  • Graceful error handling                          │
│  • Automatic recovery                               │
│  • Proper memory cleanup                            │
└─────────────────────────────────────────────────────┘
```

---

**Architecture Version:** 1.0  
**Last Updated:** 2026-05-19  
**Status:** ✅ Production Ready
