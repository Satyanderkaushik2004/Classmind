# ClassMind Mobile UI

A modern, responsive mobile interface for the ClassMind real-time classroom system, built with React and Tailwind CSS.

## Features

### 🔐 Authentication
- **OTP-based Login**: Secure email verification system
- **Google OAuth**: Integrated Google authentication
- **Role-based Access**: Separate flows for teachers and students
- **Session Persistence**: Automatic login via localStorage

### 📚 Session Management
- **Create Sessions**: Start new classroom sessions with custom duration
- **Real-time Status**: Live session tracking with pause/resume/end controls
- **Session Timer**: Automatic elapsed time calculation
- **Class Code Sharing**: One-click copy for easy student access

### 👥 Student Management
- **Real-time Roster**: WebSocket-powered live student list
- **Connection Status**: Track connected students in real-time
- **Student Avatars**: Visual identification with initials
- **Join Requests**: Approve/reject student join requests

### 📊 Analytics Dashboard
- **MCQ Understanding**: Track student comprehension
- **Participation Rate**: Monitor class engagement
- **Tests Created**: Track assessment creation
- **Topics Covered**: Monitor curriculum progress
- **Historical Charts**: Visual trend analysis

### 🚀 Test Mode
- **Quick Launch**: Start tests with one click
- **Session Integration**: Seamlessly integrated with active sessions
- **Test State Management**: Track test progress

### 🤖 AI Teaching Insights
- **Performance Tracking**: AI-powered class performance analysis
- **Improvement Metrics**: Track progress over time
- **Trend Visualization**: Historical performance charts

### ⚠️ Student Risk Monitor
- **At-risk Detection**: Identify struggling students
- **Progress Tracking**: Monitor completion rates
- **Alert System**: Early warning for students needing attention

### 💬 Real-time Communication
- **WebSocket Integration**: Real-time updates
- **Chat System**: Teacher-student messaging
- **Notification System**: In-app alerts

## Technology Stack

- **Frontend**: React 18
- **Styling**: Tailwind CSS
- **Icons**: Lucide Icons
- **WebSocket**: Native WebSocket API
- **HTTP**: Fetch API
- **State Management**: React Context API

## Backend Integration

The mobile UI is fully integrated with the ClassMind FastAPI backend:

### API Endpoints Used

#### Authentication
- `POST /api/auth/send-otp` - Send OTP to email
- `POST /api/auth/verify-otp` - Verify OTP and login
- `POST /auth/google` - Google OAuth authentication
- `GET /api/config` - Get configuration (Google Client ID)

#### Session Management
- `POST /api/session/create` - Create new session
- `GET /api/session/{code}` - Get session details
- `GET /api/teacher/sessions` - Get teacher's sessions
- `POST /api/session/{code}/control` - Control session (start/pause/resume/end)
- `POST /api/session/{code}/join` - Join session as student
- `POST /api/session/{code}/approve/{student_id}` - Approve student
- `POST /api/session/{code}/reject/{student_id}` - Reject student

#### Student Management
- `GET /api/session/{code}/students` - Get student list

#### Task Management
- `POST /api/tasks/create` - Create new task
- `POST /api/session/{code}/tasks/send` - Send task to students
- `POST /api/session/{code}/tasks/send_current` - Send next task

#### Attendance
- `GET /api/session/{code}/attendance` - Get attendance data
- `POST /api/session/{code}/attendance/control` - Control attendance

#### Chat
- `POST /api/chat/send` - Send chat message
- `GET /api/session/{code}/chat` - Get chat history

#### Analytics
- `GET /api/session/{code}/analytics` - Get session analytics
- `GET /api/session/{code}/report` - Get session report
- `GET /api/session/{code}/leaderboard` - Get leaderboard

#### Test Mode
- `POST /api/test/start` - Start test
- `POST /api/test/end/{session_code}` - End test
- `GET /api/test/{session_code}/leaderboard` - Get test leaderboard

### WebSocket Connections

#### Teacher WebSocket
- **Endpoint**: `ws://localhost:8000/ws/teacher/{session_code}`
- **Events**:
  - `roster_update` - Student roster changes
  - `task_sent` - Task delivery confirmation
  - `attendance_update` - Attendance changes
  - `student_disconnected` - Student disconnect notification

#### Student WebSocket
- **Endpoint**: `ws://localhost:8000/ws/student/{session_code}/{student_id}`
- **Events**:
  - `new_task` - New task received
  - `task_update` - Task status updates
  - `chat_message` - New chat messages

## Setup Instructions

### Prerequisites

1. **Backend Running**: Ensure the ClassMind FastAPI backend is running on `http://localhost:8000`
2. **Environment Variables**: Configure the following in your backend `.env`:
   ```
   SENDGRID_API_KEY=your_sendgrid_key
   GOOGLE_CLIENT_ID=your_google_client_id
   OPENROUTER_API_KEY=your_openrouter_key (or GEMINI_API_KEY)
   ```

### Installation

1. Navigate to the mobile-ui directory:
   ```bash
   cd mobile-ui
   ```

2. Start a local server (Python example):
   ```bash
   python -m http.server 8080
   ```

3. Open your browser and navigate to:
   ```
   http://localhost:8080
   ```

### Configuration

Update the API base URLs in `app.js` if your backend is running on a different port or host:

```javascript
const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000';
```

## Usage

### Teacher Login

1. Open the app in your browser
2. Enter your name and email
3. Select "Teacher" role
4. Click "Send OTP"
5. Check your email for the OTP code
6. Enter the OTP and click "Verify & Login"

### Creating a Session

1. After login, you'll see the dashboard
2. Click "Create Session" in the Live Session card
3. Enter session name and duration
4. Click "Create Session"
5. Share the class code with students

### Managing a Live Session

- **Pause Session**: Temporarily pause the session
- **Resume Session**: Resume a paused session
- **End Session**: Terminate the session
- **View Details**: See detailed session information

### Starting a Test

1. Ensure you have an active session
2. Click "Launch Test" in the Test Mode card
3. The test will be sent to all connected students

### Monitoring Students

- **Live Roster**: See connected students in real-time
- **Risk Monitor**: Identify at-risk students
- **Analytics**: View performance metrics

## Component Structure

```
app.js
├── API Service Layer
│   ├── Authentication
│   ├── Session Management
│   ├── Student Management
│   ├── Task Management
│   ├── Attendance
│   ├── Chat
│   ├── Analytics
│   └── Test Mode
├── WebSocket Manager
│   ├── Connection Management
│   ├── Event Handling
│   └── Reconnection Logic
├── Authentication
│   ├── Auth Context
│   ├── Login Screen
│   └── Session Management
├── UI Components
│   ├── Header
│   ├── Greeting Section
│   ├── Live Session Card
│   ├── Performance Cards
│   ├── Test Mode Card
│   ├── AI Teaching Insights
│   ├── Student Risk Monitor
│   ├── Bottom Navigation
│   └── Create Session Modal
└── Main App
    ├── Dashboard
    └── App Component
```

## Customization

### Styling

The app uses Tailwind CSS for styling. You can customize colors and styles by modifying the Tailwind classes in the components.

### API Integration

To add new API endpoints, add them to the `api` object in `app.js`:

```javascript
const api = {
    // ... existing endpoints
    myNewEndpoint: async (param) => {
        const response = await fetch(`${API_BASE_URL}/api/my-endpoint?param=${param}`);
        return response.json();
    }
};
```

### WebSocket Events

To handle new WebSocket events, add listeners in the component:

```javascript
useEffect(() => {
    if (session?.code) {
        wsManager.connect(
            `${WS_BASE_URL}/ws/teacher/${session.code}`,
            (data) => {
                if (data.type === 'my_new_event') {
                    // Handle the event
                }
            }
        );
        
        return () => wsManager.disconnect();
    }
}, [session?.code]);
```

## Troubleshooting

### Backend Connection Issues

If you see connection errors:

1. Verify the backend is running: `curl http://localhost:8000/health`
2. Check the API_BASE_URL in app.js
3. Ensure CORS is enabled on the backend

### WebSocket Connection Issues

If WebSocket fails to connect:

1. Check the WS_BASE_URL in app.js
2. Verify the session code is correct
3. Check browser console for WebSocket errors

### OTP Not Received

If OTP emails are not sent:

1. Verify SENDGRID_API_KEY in backend .env
2. Check backend logs for email errors
3. Use debug endpoint for local testing: `/api/debug/otp?email=your@email.com`

## Development

### Adding New Features

1. Add API endpoint to the `api` service layer
2. Create state variables in the Dashboard component
3. Add UI components as needed
4. Connect components with props and callbacks
5. Add WebSocket listeners for real-time updates

### Testing

For local testing without email:

1. Use the debug OTP endpoint: `/api/debug/otp?email=your@email.com`
2. The OTP will be printed in the backend console

## Security Considerations

- **HTTPS**: Use HTTPS in production
- **CORS**: Configure CORS properly on the backend
- **Authentication**: Always validate tokens on the backend
- **WebSocket Security**: Use WSS (WebSocket Secure) in production
- **Input Validation**: Validate all user inputs on the backend

## Browser Support

- Chrome/Edge (recommended)
- Firefox
- Safari
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- **Lazy Loading**: Components load on demand
- **WebSocket Reconnection**: Automatic reconnection with exponential backoff
- **State Management**: Efficient React state updates
- **Optimized Rendering**: Minimal re-renders with proper dependency arrays

## Future Enhancements

- [ ] Push notifications
- [ ] Offline support
- [ ] PWA capabilities
- [ ] Video call integration
- [ ] File sharing
- [ ] Whiteboard collaboration
- [ ] Advanced analytics
- [ ] Parent portal
- [ ] Multi-language support

## License

This project is part of the ClassMind ecosystem.

## Support

For issues or questions:
1. Check the backend logs
2. Review browser console for errors
3. Verify API endpoint availability
4. Check WebSocket connection status

---

**Built with ❤️ for modern education**
