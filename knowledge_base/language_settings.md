# Language Settings

## What it does
Manages platform localization, enabling instant, dynamic runtime translation of all UI text, labels, forms, charts, and AI chatbot responses.

## Why it exists
It supports internationalization (i18n), making the VYOM educational platform accessible to non-English speaking teachers and students.

## When it should be used
Configured at initial setup or changed mid-session via settings.

## How to use it
1. Open the language settings menu.
2. Select your language (e.g., Hindi, Punjabi, Marathi, Chinese, English).
3. The platform will translate all elements immediately without requiring a page reload.

## Best practices
Choose the platform language matching your students' instruction medium to ensure consistent teaching terms.

## Common mistakes
Assuming language switching requires a page refresh, which could sever active WebSocket sessions.

## Troubleshooting steps
If certain dynamic texts remain in English, check that the translations registry contains the corresponding key.

## Related features
Profile Settings, Multilingual Support
