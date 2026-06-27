# Session Management

## What it does
Governs the lifecycle of a class session from initialization, student registration, state changes (waiting, active, paused, ended), to cleanup and database persistence.

## Why it exists
It secures classroom data, manages student connections, and guarantees state continuity across network reconnects.

## When it should be used
Active from the creation of the class until its reports are saved.

## How to use it
1. Teacher clicks 'Create Class Session' to instantiate session states.
2. Server assigns a unique 6-digit code.
3. Manage the active session via classroom controls.
4. End the session to archive data and compile grading reports.

## Best practices
Avoid running multiple active sessions simultaneously under a single teacher account to prevent socket collision.

## Common mistakes
Closing the teacher server window instead of ending the session, which leaves session memory in an uncompiled state.

## Troubleshooting steps
If a session code is reported as expired, check the session registry or create a new session.

## Related features
Classroom Controls, Waiting Room
