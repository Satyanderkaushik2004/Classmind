# Export Features

## What it does
Allows downloading classroom data including grades, attendance logs, and analytical reports in PDF and Microsoft Excel formats.

## Why it exists
It supports offline grading, printing, archiving, and integration with external school databases.

## When it should be used
Used after class completion or when downloading mid-session rosters.

## How to use it
1. Navigate to the Reports or Attendance tab.
2. Click 'Export PDF' or 'Export Excel'.
3. The server compiles the files and triggers a local browser download.

## Best practices
Export Excel sheets for grade calculations and PDF formats for printing/sharing.

## Common mistakes
Opening exported spreadsheets in legacy excel viewers that don't support modern xlsx formats.

## Troubleshooting steps
If Excel generation fails, verify the openpyxl library is installed on the Python server.

## Related features
Reports, Attendance Tracking
