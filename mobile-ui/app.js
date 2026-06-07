const { useState, useEffect, useContext, createContext } = React;

// API Configuration
const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000';

// API Service Layer
const api = {
    // Auth
    sendOtp: async (email, name, role) => {
        const response = await fetch(`${API_BASE_URL}/api/auth/send-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, name, role })
        });
        return response.json();
    },
    
    verifyOtp: async (email, otp) => {
        const response = await fetch(`${API_BASE_URL}/api/auth/verify-otp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, otp })
        });
        return response.json();
    },
    
    googleAuth: async (token) => {
        const response = await fetch(`${API_BASE_URL}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token })
        });
        return response.json();
    },
    
    getConfig: async () => {
        const response = await fetch(`${API_BASE_URL}/api/config`);
        return response.json();
    },
    
    // Session
    createSession: async (data) => {
        const response = await fetch(`${API_BASE_URL}/api/session/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    getSession: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}`);
        return response.json();
    },
    
    getTeacherSessions: async (email) => {
        const response = await fetch(`${API_BASE_URL}/api/teacher/sessions?email=${email}`);
        return response.json();
    },
    
    controlSession: async (code, action) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/control?action=${action}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    joinSession: async (code, name, roll, cls, email) => {
        const params = new URLSearchParams({ name, roll, class: cls, email });
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/join?${params}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    approveStudent: async (code, studentId) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/approve/${studentId}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    rejectStudent: async (code, studentId) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/reject/${studentId}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    // Students
    getStudents: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/students`);
        return response.json();
    },
    
    // Tasks
    createTask: async (data) => {
        const response = await fetch(`${API_BASE_URL}/api/tasks/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    sendTask: async (code, data) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/tasks/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    sendCurrentTask: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/tasks/send_current`, {
            method: 'POST'
        });
        return response.json();
    },
    
    // Attendance
    getAttendance: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/attendance`);
        return response.json();
    },
    
    controlAttendance: async (code, action) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/attendance/control?action=${action}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    // Chat
    sendMessage: async (data) => {
        const response = await fetch(`${API_BASE_URL}/api/chat/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    getChat: async (code, chatType = 'global') => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/chat?chat_type=${chatType}`);
        return response.json();
    },
    
    // Analytics
    getAnalytics: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/analytics`);
        return response.json();
    },
    
    getReport: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/report`);
        return response.json();
    },
    
    getLeaderboard: async (code) => {
        const response = await fetch(`${API_BASE_URL}/api/session/${code}/leaderboard`);
        return response.json();
    },
    
    // Test
    startTest: async (data) => {
        const response = await fetch(`${API_BASE_URL}/api/test/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    endTest: async (sessionCode) => {
        const response = await fetch(`${API_BASE_URL}/api/test/end/${sessionCode}`, {
            method: 'POST'
        });
        return response.json();
    }
};

// Auth Context
const AuthContext = createContext(null);

const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    
    useEffect(() => {
        const storedUser = localStorage.getItem('classmind_user');
        if (storedUser) {
            setUser(JSON.parse(storedUser));
        }
        setLoading(false);
    }, []);
    
    const login = async (userData) => {
        setUser(userData);
        localStorage.setItem('classmind_user', JSON.stringify(userData));
    };
    
    const logout = () => {
        setUser(null);
        localStorage.removeItem('classmind_user');
    };
    
    return (
        <AuthContext.Provider value={{ user, login, logout, loading }}>
            {children}
        </AuthContext.Provider>
    );
};

// Icon Components using Lucide
const Icon = ({ name, size = 20, className = "" }) => {
    useEffect(() => {
        lucide.createIcons();
    }, [name]);
    
    return <i data-lucide={name} className={className} style={{ width: size, height: size }}></i>;
};

// WebSocket Manager
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.listeners = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }
    
    connect(url, onMessage, onOpen, onClose, onError) {
        if (this.ws) {
            this.ws.close();
        }
        
        this.ws = new WebSocket(url);
        
        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            if (onOpen) onOpen();
        };
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (onMessage) onMessage(data);
                
                // Notify specific listeners
                const eventType = data.type;
                if (this.listeners.has(eventType)) {
                    this.listeners.get(eventType).forEach(callback => callback(data));
                }
            } catch (e) {
                console.error('WebSocket message parse error:', e);
            }
        };
        
        this.ws.onclose = () => {
            if (onClose) onClose();
            this.attemptReconnect(url, onMessage, onOpen, onClose, onError);
        };
        
        this.ws.onerror = (error) => {
            if (onError) onError(error);
        };
    }
    
    attemptReconnect(url, onMessage, onOpen, onClose, onError) {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                this.connect(url, onMessage, onOpen, onClose, onError);
            }, 3000 * this.reconnectAttempts);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    on(eventType, callback) {
        if (!this.listeners.has(eventType)) {
            this.listeners.set(eventType, []);
        }
        this.listeners.get(eventType).push(callback);
    }
    
    off(eventType, callback) {
        if (this.listeners.has(eventType)) {
            const callbacks = this.listeners.get(eventType);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.listeners.clear();
    }
}

const wsManager = new WebSocketManager();

// Login Screen
const LoginScreen = () => {
    const { login } = useContext(AuthContext);
    const [email, setEmail] = useState('');
    const [name, setName] = useState('');
    const [role, setRole] = useState('teacher');
    const [otp, setOtp] = useState('');
    const [step, setStep] = useState('email'); // email, otp
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    
    const handleSendOtp = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        
        try {
            const result = await api.sendOtp(email, name, role);
            if (result.success) {
                setStep('otp');
            } else {
                setError(result.message || 'Failed to send OTP');
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };
    
    const handleVerifyOtp = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        
        try {
            const result = await api.verifyOtp(email, otp);
            if (result.success) {
                login({
                    email: result.email,
                    name: result.name,
                    role: result.role,
                    token: result.token
                });
            } else {
                setError(result.message || 'Invalid OTP');
            }
        } catch (err) {
            setError('Network error. Please try again.');
        } finally {
            setLoading(false);
        }
    };
    
    return (
        <div className="min-h-screen flex items-center justify-center p-4">
            <div className="glass-card rounded-3xl p-8 w-full max-w-md shadow-soft">
                <div className="text-center mb-8">
                    <div className="w-20 h-20 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mx-auto mb-4">
                        <Icon name="graduation-cap" size={40} className="text-white" />
                    </div>
                    <h1 className="text-2xl font-bold text-gray-800">ClassMind</h1>
                    <p className="text-gray-600">Real-time Classroom System</p>
                </div>
                
                {error && (
                    <div className="bg-red-100 border border-red-300 text-red-700 px-4 py-3 rounded-xl mb-4">
                        {error}
                    </div>
                )}
                
                {step === 'email' ? (
                    <form onSubmit={handleSendOtp}>
                        <div className="mb-4">
                            <label className="block text-gray-700 text-sm font-medium mb-2">Name</label>
                            <input
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                                placeholder="Enter your name"
                                required
                            />
                        </div>
                        
                        <div className="mb-4">
                            <label className="block text-gray-700 text-sm font-medium mb-2">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                                placeholder="Enter your email"
                                required
                            />
                        </div>
                        
                        <div className="mb-6">
                            <label className="block text-gray-700 text-sm font-medium mb-2">I am a</label>
                            <div className="flex gap-4">
                                <button
                                    type="button"
                                    onClick={() => setRole('teacher')}
                                    className={`flex-1 py-3 rounded-xl font-medium transition ${
                                        role === 'teacher' 
                                            ? 'bg-purple-600 text-white' 
                                            : 'bg-gray-100 text-gray-700'
                                    }`}
                                >
                                    Teacher
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setRole('student')}
                                    className={`flex-1 py-3 rounded-xl font-medium transition ${
                                        role === 'student' 
                                            ? 'bg-purple-600 text-white' 
                                            : 'bg-gray-100 text-gray-700'
                                    }`}
                                >
                                    Student
                                </button>
                            </div>
                        </div>
                        
                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold py-3 rounded-xl hover:opacity-90 transition disabled:opacity-50"
                        >
                            {loading ? 'Sending OTP...' : 'Send OTP'}
                        </button>
                    </form>
                ) : (
                    <form onSubmit={handleVerifyOtp}>
                        <div className="mb-6">
                            <label className="block text-gray-700 text-sm font-medium mb-2">Enter OTP</label>
                            <input
                                type="text"
                                value={otp}
                                onChange={(e) => setOtp(e.target.value)}
                                className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-purple-500 text-center text-2xl tracking-widest"
                                placeholder="••••••"
                                maxLength={6}
                                required
                            />
                            <p className="text-gray-500 text-sm mt-2">Check your email for the OTP</p>
                        </div>
                        
                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold py-3 rounded-xl hover:opacity-90 transition disabled:opacity-50"
                        >
                            {loading ? 'Verifying...' : 'Verify & Login'}
                        </button>
                        
                        <button
                            type="button"
                            onClick={() => setStep('email')}
                            className="w-full mt-3 text-gray-600 font-medium py-2 hover:text-gray-800"
                        >
                            Back
                        </button>
                    </form>
                )}
            </div>
        </div>
    );
};

// Header Component
const Header = ({ user, onLogout }) => {
    const [currentTime, setCurrentTime] = useState(new Date());
    
    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);
    
    const formatTime = (date) => {
        return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    };
    
    return (
        <div className="bg-white/10 backdrop-blur-lg px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                    <Icon name="menu" size={18} className="text-white" />
                </div>
                <div>
                    <h1 className="text-white font-bold text-lg">ClassMind</h1>
                    <p className="text-white/70 text-xs">Real-time Classroom System</p>
                </div>
            </div>
            <div className="flex items-center gap-3">
                <span className="text-white font-semibold">{formatTime(currentTime)}</span>
                <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center relative">
                    <Icon name="bell" size={18} className="text-white" />
                    <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-white text-xs flex items-center justify-center">3</span>
                </div>
                <button onClick={onLogout} className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                    <Icon name="log-out" size={18} className="text-white" />
                </button>
            </div>
        </div>
    );
};

// Greeting Section
const GreetingSection = ({ user }) => {
    const getGreeting = () => {
        const hour = new Date().getHours();
        if (hour < 12) return 'Good morning';
        if (hour < 17) return 'Good afternoon';
        return 'Good evening';
    };
    
    return (
        <div className="px-4 py-4">
            <div className="flex items-center gap-3">
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-purple-400 to-pink-400 flex items-center justify-center shadow-lg">
                    <Icon name="user" size={28} className="text-white" />
                </div>
                <div className="flex-1">
                    <p className="text-white/80 text-sm">{getGreeting()},</p>
                    <h2 className="text-white font-bold text-xl">{user?.name || 'Teacher'}!</h2>
                </div>
                <div className="w-10 h-10 rounded-full bg-purple-500/30 flex items-center justify-center">
                    <Icon name="brain" size={20} className="text-purple-200" />
                </div>
            </div>
        </div>
    );
};

// Live Session Card
const LiveSessionCard = ({ session, onControlSession, onViewDetails }) => {
    const [sessionTime, setSessionTime] = useState(0);
    const [connectedStudents, setConnectedStudents] = useState([]);
    
    useEffect(() => {
        if (session?.started_at) {
            const startTime = new Date(session.started_at).getTime();
            const timer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - startTime) / 1000);
                setSessionTime(elapsed);
            }, 1000);
            return () => clearInterval(timer);
        }
    }, [session?.started_at]);
    
    useEffect(() => {
        if (session?.code) {
            // Connect to WebSocket for real-time updates
            wsManager.connect(
                `${WS_BASE_URL}/ws/teacher/${session.code}`,
                (data) => {
                    if (data.type === 'roster_update') {
                        setConnectedStudents(data.active || []);
                    }
                }
            );
            
            return () => wsManager.disconnect();
        }
    }, [session?.code]);
    
    const formatSessionTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };
    
    const handleCopyCode = () => {
        if (session?.code) {
            navigator.clipboard.writeText(session.code);
        }
    };
    
    if (!session) {
        return (
            <div className="mx-4 mb-4 glass-card rounded-2xl p-5 shadow-soft">
                <div className="text-center py-8">
                    <Icon name="plus-circle" size={48} className="text-purple-400 mx-auto mb-3" />
                    <h3 className="text-gray-800 font-bold text-lg mb-2">No Active Session</h3>
                    <p className="text-gray-600 text-sm mb-4">Create a new session to start teaching</p>
                    <button 
                        onClick={() => onControlSession('create')}
                        className="bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold px-6 py-3 rounded-xl"
                    >
                        Create Session
                    </button>
                </div>
            </div>
        );
    }
    
    const isLive = session.status === 'active';
    const isPaused = session.status === 'paused';
    
    return (
        <div className="mx-4 mb-4 rounded-2xl gradient-purple p-5 shadow-glow">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-400 animate-pulse-slow' : 'bg-yellow-400'}`}></div>
                    <span className="text-white font-semibold text-sm">
                        {isLive ? 'LIVE SESSION' : isPaused ? 'PAUSED' : 'SESSION'}
                    </span>
                </div>
                <button className="text-white/80 hover:text-white">
                    <Icon name="more-horizontal" size={20} />
                </button>
            </div>
            
            <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-white/20 rounded-xl p-3">
                    <p className="text-white/70 text-xs mb-1">CLASS CODE</p>
                    <div className="flex items-center gap-2">
                        <span className="text-white font-bold text-lg">{session.code}</span>
                        <button onClick={handleCopyCode}>
                            <Icon name="copy" size={16} className="text-white/70" />
                        </button>
                    </div>
                </div>
                <div className="bg-white/20 rounded-xl p-3">
                    <p className="text-white/70 text-xs mb-1">STUDENTS</p>
                    <div className="flex items-center gap-2">
                        <Icon name="users" size={16} className="text-white/70" />
                        <span className="text-white font-bold text-lg">{connectedStudents.length} Connected</span>
                    </div>
                </div>
            </div>
            
            <div className="bg-white/20 rounded-xl p-3 mb-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Icon name="clock" size={16} className="text-white/70" />
                        <span className="text-white/70 text-sm">Session Time</span>
                    </div>
                    <span className="text-white font-bold">{formatSessionTime(sessionTime)}</span>
                </div>
            </div>
            
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center">
                    {connectedStudents.slice(0, 3).map((student, i) => (
                        <div key={student.id} className="w-8 h-8 rounded-full border-2 border-white flex items-center justify-center" style={{ marginLeft: i === 0 ? '0' : '-8px' }}>
                            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center">
                                <span className="text-white text-xs font-bold">{student.name.charAt(0)}</span>
                            </div>
                        </div>
                    ))}
                    {connectedStudents.length > 3 && (
                        <div className="w-8 h-8 rounded-full bg-white/30 flex items-center justify-center -ml-2 ml-1">
                            <span className="text-white text-xs font-semibold">+{connectedStudents.length - 3}</span>
                        </div>
                    )}
                </div>
                <button onClick={onViewDetails} className="text-white/80 text-sm font-medium">View Details →</button>
            </div>
            
            <div className="flex gap-3">
                {isLive ? (
                    <button 
                        onClick={() => onControlSession('pause')}
                        className="flex-1 bg-white text-purple-600 font-semibold py-3 rounded-xl hover:bg-white/90 transition"
                    >
                        Pause Session
                    </button>
                ) : (
                    <button 
                        onClick={() => onControlSession('resume')}
                        className="flex-1 bg-white text-purple-600 font-semibold py-3 rounded-xl hover:bg-white/90 transition"
                    >
                        Resume Session
                    </button>
                )}
                <button 
                    onClick={() => onControlSession('end')}
                    className="flex-1 bg-white/20 text-white font-semibold py-3 rounded-xl hover:bg-white/30 transition"
                >
                    End Session
                </button>
            </div>
        </div>
    );
};

// Performance Card
const PerformanceCard = ({ title, value, icon, color, data }) => {
    const colorClasses = {
        purple: "from-purple-500 to-purple-600",
        blue: "from-blue-500 to-blue-600",
        green: "from-green-500 to-green-600",
        orange: "from-orange-500 to-orange-600",
    };
    
    const chartData = data || [40, 60, 45, 80, 55, 70, 65];
    
    return (
        <div className="glass-card rounded-2xl p-4 shadow-soft">
            <div className="flex items-center justify-between mb-2">
                <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${colorClasses[color]} flex items-center justify-center`}>
                    <Icon name={icon} size={18} className="text-white" />
                </div>
                <div className="text-right">
                    <p className="text-2xl font-bold text-gray-800">{value}</p>
                </div>
            </div>
            <p className="text-gray-600 text-sm font-medium">{title}</p>
            <div className="mt-2 h-8 flex items-end gap-1">
                {chartData.map((height, i) => (
                    <div key={i} className="flex-1 bg-gradient-to-t from-purple-200 to-purple-400 rounded-t" style={{ height: `${height}%` }}></div>
                ))}
            </div>
        </div>
    );
};

// Performance Cards Grid
const PerformanceCards = ({ analytics }) => {
    const data = analytics || {};
    
    return (
        <div className="px-4 mb-4">
            <div className="grid grid-cols-2 gap-3">
                <PerformanceCard 
                    title="MCQ Understanding" 
                    value={`${data.mcqUnderstanding || 0}%`} 
                    icon="brain" 
                    color="purple"
                    data={data.mcqHistory}
                />
                <PerformanceCard 
                    title="Participation" 
                    value={`${data.participation || 100}%`} 
                    icon="users" 
                    color="blue"
                    data={data.participationHistory}
                />
                <PerformanceCard 
                    title="Tests Created" 
                    value={data.testsCreated || 4} 
                    icon="file-text" 
                    color="green"
                    data={data.testsHistory}
                />
                <PerformanceCard 
                    title="Topics Covered" 
                    value={data.topicsCovered || 1} 
                    icon="graduation-cap" 
                    color="orange"
                    data={data.topicsHistory}
                />
            </div>
        </div>
    );
};

// Test Mode Card
const TestModeCard = ({ session, onStartTest }) => {
    const handleLaunchTest = async () => {
        if (session?.code) {
            await onStartTest(session.code);
        }
    };
    
    return (
        <div className="mx-4 mb-4 glass-card rounded-2xl p-5 shadow-soft">
            <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center flex-shrink-0">
                    <Icon name="rocket" size={28} className="text-white" />
                </div>
                <div className="flex-1">
                    <h3 className="font-bold text-gray-800 text-lg mb-1">Test Mode</h3>
                    <p className="text-gray-600 text-sm mb-3">Create & launch tests for your class in seconds.</p>
                    <button 
                        onClick={handleLaunchTest}
                        disabled={!session}
                        className="bg-gradient-to-r from-orange-400 to-red-500 text-white font-semibold px-4 py-2 rounded-xl flex items-center gap-2 hover:opacity-90 transition disabled:opacity-50"
                    >
                        <Icon name="rocket" size={16} />
                        Launch Test
                    </button>
                </div>
            </div>
        </div>
    );
};

// AI Teaching Insights Card
const AITeachingInsights = ({ insights }) => {
    const data = insights || {
        message: "Coding task completion rate is tracking excellently.",
        improvement: "+18%",
        history: [30, 45, 35, 60, 50, 75, 65, 80, 70, 85]
    };
    
    return (
        <div className="mx-4 mb-4 glass-card rounded-2xl p-5 shadow-soft">
            <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-400 to-pink-500 flex items-center justify-center flex-shrink-0">
                    <Icon name="sparkles" size={28} className="text-white" />
                </div>
                <div className="flex-1">
                    <h3 className="font-bold text-gray-800 text-lg mb-1">AI Teaching Insights</h3>
                    <p className="text-gray-600 text-sm mb-3">{data.message}</p>
                    <div className="flex items-center gap-2">
                        <span className="bg-green-100 text-green-600 font-bold px-3 py-1 rounded-full text-sm">{data.improvement}</span>
                        <div className="flex-1 h-8 flex items-end gap-1">
                            {data.history.map((height, i) => (
                                <div key={i} className="flex-1 bg-gradient-to-t from-purple-300 to-purple-500 rounded-t" style={{ height: `${height}%` }}></div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

// Student Risk Monitor Card
const StudentRiskMonitor = ({ riskData }) => {
    const data = riskData || {
        atRiskCount: 1,
        student: { name: 'John Doe', completion: 0 }
    };
    
    return (
        <div className="mx-4 mb-4 glass-card rounded-2xl p-5 shadow-soft">
            <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-red-400 to-orange-500 flex items-center justify-center flex-shrink-0">
                    <Icon name="shield-alert" size={28} className="text-white" />
                </div>
                <div className="flex-1">
                    <h3 className="font-bold text-gray-800 text-lg mb-1">Student Risk Monitor</h3>
                    <p className="text-gray-600 text-sm mb-3">{data.atRiskCount} student{data.atRiskCount !== 1 ? 's' : ''} need{data.atRiskCount === 1 ? 's' : ''} attention.</p>
                    {data.student && (
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-400 to-purple-400 flex items-center justify-center">
                                <span className="text-white text-xs font-bold">{data.student.name.charAt(0)}</span>
                            </div>
                            <div className="flex-1">
                                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                                    <div className="h-full bg-gradient-to-r from-red-400 to-orange-400 rounded-full" style={{ width: `${data.student.completion}%` }}></div>
                                </div>
                                <p className="text-gray-500 text-xs mt-1">{data.student.completion}% completion</p>
                            </div>
                            <button className="text-purple-600 font-semibold text-sm">View →</button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

// Bottom Navigation
const BottomNavigation = ({ activeTab, onTabChange }) => {
    const tabs = [
        { id: 'dashboard', icon: 'layout-dashboard', label: 'Dashboard' },
        { id: 'tasks', icon: 'list-todo', label: 'Tasks' },
        { id: 'attendance', icon: 'user-check', label: 'Attendance' },
        { id: 'chat', icon: 'message-circle', label: 'Chat' },
        { id: 'reports', icon: 'bar-chart-3', label: 'Reports' },
    ];
    
    return (
        <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-2 py-2 safe-area-bottom">
            <div className="flex items-center justify-around">
                {tabs.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => onTabChange(tab.id)}
                        className={`flex flex-col items-center gap-1 px-3 py-2 rounded-xl transition ${
                            activeTab === tab.id ? 'bg-purple-100' : 'hover:bg-gray-100'
                        }`}
                    >
                        <Icon 
                            name={tab.icon} 
                            size={20} 
                            className={activeTab === tab.id ? 'text-purple-600' : 'text-gray-400'} 
                        />
                        <span className={`text-xs font-medium ${
                            activeTab === tab.id ? 'text-purple-600' : 'text-gray-400'
                        }`}>
                            {tab.label}
                        </span>
                    </button>
                ))}
            </div>
        </div>
    );
};

// Create Session Modal
const CreateSessionModal = ({ isOpen, onClose, onCreate }) => {
    const [sessionName, setSessionName] = useState('');
    const [duration, setDuration] = useState(60);
    const [loading, setLoading] = useState(false);
    
    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        
        try {
            await onCreate({
                session_name: sessionName,
                duration_mins: duration,
                teacher_name: 'Teacher', // Will be replaced with actual user name
                teacher_email: 'teacher@example.com' // Will be replaced with actual user email
            });
            onClose();
        } catch (error) {
            console.error('Failed to create session:', error);
        } finally {
            setLoading(false);
        }
    };
    
    if (!isOpen) return null;
    
    return (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="glass-card rounded-2xl p-6 w-full max-w-md">
                <h2 className="text-xl font-bold text-gray-800 mb-4">Create New Session</h2>
                <form onSubmit={handleSubmit}>
                    <div className="mb-4">
                        <label className="block text-gray-700 text-sm font-medium mb-2">Session Name</label>
                        <input
                            type="text"
                            value={sessionName}
                            onChange={(e) => setSessionName(e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            placeholder="Enter session name"
                            required
                        />
                    </div>
                    
                    <div className="mb-6">
                        <label className="block text-gray-700 text-sm font-medium mb-2">Duration (minutes)</label>
                        <input
                            type="number"
                            value={duration}
                            onChange={(e) => setDuration(parseInt(e.target.value))}
                            min="1"
                            max="120"
                            className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                            required
                        />
                    </div>
                    
                    <div className="flex gap-3">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 bg-gray-100 text-gray-700 font-semibold py-3 rounded-xl hover:bg-gray-200 transition"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold py-3 rounded-xl hover:opacity-90 transition disabled:opacity-50"
                        >
                            {loading ? 'Creating...' : 'Create Session'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

// Main Dashboard Component
const Dashboard = ({ user, onLogout }) => {
    const [activeTab, setActiveTab] = useState('dashboard');
    const [session, setSession] = useState(null);
    const [analytics, setAnalytics] = useState(null);
    const [insights, setInsights] = useState(null);
    const [riskData, setRiskData] = useState(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [loading, setLoading] = useState(false);
    
    // Load initial data
    useEffect(() => {
        loadDashboardData();
    }, [user]);
    
    const loadDashboardData = async () => {
        if (!user?.email) return;
        
        try {
            setLoading(true);
            
            // Load teacher sessions
            const sessions = await api.getTeacherSessions(user.email);
            if (sessions && sessions.length > 0) {
                // Get the most recent active session
                const activeSession = sessions.find(s => s.status === 'active') || sessions[0];
                const sessionDetails = await api.getSession(activeSession.code);
                setSession(sessionDetails);
                
                // Load analytics for the session
                const analyticsData = await api.getAnalytics(activeSession.code);
                setAnalytics(analyticsData);
                
                // Load report for insights
                const reportData = await api.getReport(activeSession.code);
                setInsights({
                    message: "Class performance is tracking well",
                    improvement: "+18%",
                    history: reportData?.history || [30, 45, 35, 60, 50, 75, 65, 80, 70, 85]
                });
                
                // Calculate risk data
                const students = await api.getStudents(activeSession.code);
                const atRiskStudents = students.active?.filter(s => s.score < 50) || [];
                setRiskData({
                    atRiskCount: atRiskStudents.length,
                    student: atRiskStudents[0] ? { name: atRiskStudents[0].name, completion: atRiskStudents[0].score || 0 } : null
                });
            }
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        } finally {
            setLoading(false);
        }
    };
    
    const handleControlSession = async (action) => {
        if (action === 'create') {
            setShowCreateModal(true);
            return;
        }
        
        if (!session?.code) return;
        
        try {
            await api.controlSession(session.code, action);
            
            if (action === 'end') {
                setSession(null);
                setAnalytics(null);
            } else {
                // Refresh session data
                const updatedSession = await api.getSession(session.code);
                setSession(updatedSession);
            }
        } catch (error) {
            console.error('Failed to control session:', error);
        }
    };
    
    const handleCreateSession = async (sessionData) => {
        try {
            const result = await api.createSession({
                ...sessionData,
                teacher_name: user?.name || 'Teacher',
                teacher_email: user?.email || 'teacher@example.com'
            });
            
            // Load the new session
            const sessionDetails = await api.getSession(result.session_code);
            setSession(sessionDetails);
            
            // Load initial analytics
            const analyticsData = await api.getAnalytics(result.session_code);
            setAnalytics(analyticsData);
        } catch (error) {
            console.error('Failed to create session:', error);
            throw error;
        }
    };
    
    const handleStartTest = async (sessionCode) => {
        try {
            await api.startTest({ session_code: sessionCode });
            alert('Test started successfully!');
        } catch (error) {
            console.error('Failed to start test:', error);
            alert('Failed to start test. Please try again.');
        }
    };
    
    const handleViewDetails = () => {
        // Navigate to session details view
        setActiveTab('tasks');
    };
    
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-center">
                    <div className="w-12 h-12 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                    <p className="text-white">Loading...</p>
                </div>
            </div>
        );
    }
    
    return (
        <div className="min-h-screen pb-20">
            <Header user={user} onLogout={onLogout} />
            <GreetingSection user={user} />
            
            {activeTab === 'dashboard' && (
                <>
                    <LiveSessionCard 
                        session={session} 
                        onControlSession={handleControlSession}
                        onViewDetails={handleViewDetails}
                    />
                    <PerformanceCards analytics={analytics} />
                    <TestModeCard session={session} onStartTest={handleStartTest} />
                    <AITeachingInsights insights={insights} />
                    <StudentRiskMonitor riskData={riskData} />
                </>
            )}
            
            {activeTab === 'tasks' && (
                <div className="px-4 py-8">
                    <div className="glass-card rounded-2xl p-6 shadow-soft">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Tasks</h2>
                        <p className="text-gray-600">Task management coming soon...</p>
                    </div>
                </div>
            )}
            
            {activeTab === 'attendance' && (
                <div className="px-4 py-8">
                    <div className="glass-card rounded-2xl p-6 shadow-soft">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Attendance</h2>
                        <p className="text-gray-600">Attendance tracking coming soon...</p>
                    </div>
                </div>
            )}
            
            {activeTab === 'chat' && (
                <div className="px-4 py-8">
                    <div className="glass-card rounded-2xl p-6 shadow-soft">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Chat</h2>
                        <p className="text-gray-600">Chat functionality coming soon...</p>
                    </div>
                </div>
            )}
            
            {activeTab === 'reports' && (
                <div className="px-4 py-8">
                    <div className="glass-card rounded-2xl p-6 shadow-soft">
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Reports</h2>
                        <p className="text-gray-600">Reports and analytics coming soon...</p>
                    </div>
                </div>
            )}
            
            <BottomNavigation activeTab={activeTab} onTabChange={setActiveTab} />
            
            <CreateSessionModal 
                isOpen={showCreateModal}
                onClose={() => setShowCreateModal(false)}
                onCreate={handleCreateSession}
            />
        </div>
    );
};

// Main App Component
const App = () => {
    const { user, login, logout, loading } = useContext(AuthContext);
    
    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-12 h-12 border-4 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
            </div>
        );
    }
    
    if (!user) {
        return <LoginScreen />;
    }
    
    return <Dashboard user={user} onLogout={logout} />;
};

// Render the app
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <AuthProvider>
        <App />
    </AuthProvider>
);
