vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update TeacherCopilot definition & state initialization & callAI
old_teacher_copilot_start = """function TeacherCopilot({
  analytics,
  roster,
  tasks,
  sessionStatus,
  sessionControl,
  setPage,
  tourMessage,
  setForceTour,
  prevSessionStatus,
  prevTasksLength,
  profilePhoto
}) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [unread, setUnread] = useState(0);
  const [listening, setListening] = useState(false);
  const [activeMode, setActiveMode] = useState('chat'); // chat | actions | insights
  const [messages, setMessages] = useState(() => {
    const greetings = [
      "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.",
      "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.",
      "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!"
    ];
    return [{ role:'bot', text: greetings[Math.floor(Math.random()*greetings.length)], ts: fmtTs(), ai: false }];
  });"""

new_teacher_copilot_start = """function TeacherCopilot({
  analytics,
  roster,
  tasks,
  sessionStatus,
  sessionControl,
  setPage,
  tourMessage,
  setForceTour,
  prevSessionStatus,
  prevTasksLength,
  profilePhoto,
  sessionCode
}) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [unread, setUnread] = useState(0);
  const [listening, setListening] = useState(false);
  const [activeMode, setActiveMode] = useState('chat'); // chat | actions | insights
  const { language } = React.useContext(AppCtx) || { language: 'en' };
  const [messages, setMessages] = useState(() => {
    const greetings = [
      "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.",
      "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.",
      "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!"
    ];
    const initialLang = localStorage.getItem('cm_lang') || 'en';
    const chosen = greetings[Math.floor(Math.random()*greetings.length)];
    return [{ role:'bot', text: translateString(chosen, initialLang), ts: fmtTs(), ai: false }];
  });

  useEffect(() => {
    setMessages(prev => {
      if (prev.length === 0) return prev;
      const first = prev[0];
      if (first.role === 'bot' && !first.ai) {
        const greetings = [
          "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.",
          "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.",
          "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!"
        ];
        const currentGreeting = greetings.find(g => translateString(g, language) === first.text) || greetings[0];
        return [{
          ...first,
          text: translateString(currentGreeting, language)
        }, ...prev.slice(1)];
      }
      return prev;
    });
  }, [language]);"""

# 2. Update callAI inside TeacherCopilot
old_teacher_call_ai = """  // ── Call Anthropic API ─────────────────────────────────────────────
  async function callAI(userMessage) {
    const ctx = buildContext();
    const msgHistory = messages.slice(-14).map(m => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.text.replace(/<[^>]+>/g,'')
    })).filter(m => m.role === 'user' || m.role === 'assistant');

    try {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      const resp = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortRef.current.signal,
        body: JSON.stringify({
          model: 'claude-sonnet-4-6',
          max_tokens: 700,
          system: ctx,
          messages: [...msgHistory, { role:'user', content: userMessage }]
        })
      });
      if (!resp.ok) throw new Error('API ' + resp.status);
      const data = await resp.json();
      return { text: data.content?.[0]?.text || 'Sorry, I got an empty response.', ai: true };
    } catch(e) {
      if (e.name === 'AbortError') return null;
      return { text: getLocalReply(userMessage.toLowerCase()), ai: false };
    }
  }"""

new_teacher_call_ai = """  // ── Call AI Backend ────────────────────────────────────────────────
  async function callAI(userMessage) {
    const msgHistory = messages.slice(-14).map(m => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.text.replace(/<[^>]+>/g,'')
    })).filter(m => m.role === 'user' || m.role === 'assistant');

    try {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      const api_key = (() => { try { const user = JSON.parse(localStorage.getItem('cm_user')||'{}'); return user.apiKey || ''; } catch { return ''; } })();
      
      const resp = await fetch('/api/ai/chatbot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortRef.current.signal,
        body: JSON.stringify({
          message: userMessage,
          history: msgHistory,
          session_code: sessionCode || null,
          student_id: null,
          language: language,
          role: 'teacher',
          api_key: api_key || null
        })
      });
      if (!resp.ok) throw new Error('API status ' + resp.status);
      const data = await resp.json();
      return { text: data.response || 'Sorry, I got an empty response.', ai: true };
    } catch(e) {
      if (e.name === 'AbortError') return null;
      console.error('[TEACHER COPILET ERROR]', e);
      return { text: getLocalReply(userMessage.toLowerCase()), ai: false };
    }
  }"""

# 3. Update StudentCopilotLight definition & callAI
old_student_copilot_start = """function StudentCopilotLight({
  currentTask, submitted, result, answeredCount, correctCount, selected, shortAnswer, timeSpent,
  studentPhoto, studentName
}) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [messages, setMessages] = useState([]);"""

new_student_copilot_start = """function StudentCopilotLight({
  currentTask, submitted, result, answeredCount, correctCount, selected, shortAnswer, timeSpent,
  studentPhoto, studentName,
  sessionCode, studentId
}) {
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [messages, setMessages] = useState([]);
  const { language } = React.useContext(AppCtx) || { language: 'en' };"""

old_student_call_ai = """  // ── Call AI ────────────────────────────────────────────────────────
  async function callAI(userMessage) {
    try {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      const resp = await fetch('https://api.anthropic.com/v1/messages', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        signal:abortRef.current.signal,
        body: JSON.stringify({
          model:'claude-sonnet-4-6',
          max_tokens:400,
          system: buildStudentContext(),
          messages: [
            ...messages.slice(-10).map(m=>({role:m.role==='user'?'user':'assistant',content:m.text})),
            {role:'user',content:userMessage}
          ]
        })
      });
      if (!resp.ok) throw new Error('API '+resp.status);
      const data = await resp.json();
      return {text: data.content?.[0]?.text || 'Sorry, try again!', ai:true};
    } catch(e) {
      if (e.name==='AbortError') return null;
      return {text: getLocalResponse(userMessage.toLowerCase()), ai:false};
    }
  }"""

new_student_call_ai = """  // ── Call AI Backend ────────────────────────────────────────────────
  async function callAI(userMessage) {
    try {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      const api_key = (() => { try { const user = JSON.parse(localStorage.getItem('cm_user')||'{}'); return user.apiKey || ''; } catch { return ''; } })();
      
      const resp = await fetch('/api/ai/chatbot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortRef.current.signal,
        body: JSON.stringify({
          message: userMessage,
          history: messages.slice(-10).map(m => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.text.replace(/<[^>]+>/g,'')
          })).filter(m => m.role === 'user' || m.role === 'assistant'),
          session_code: sessionCode || null,
          student_id: studentId || null,
          language: language,
          role: 'student',
          api_key: api_key || null
        })
      });
      if (!resp.ok) throw new Error('API status ' + resp.status);
      const data = await resp.json();
      return { text: data.response || 'Sorry, try again!', ai: true };
    } catch(e) {
      if (e.name === 'AbortError') return null;
      console.error('[STUDENT COPILET ERROR]', e);
      return { text: getLocalResponse(userMessage.toLowerCase()), ai: false };
    }
  }"""

# 4. Update the instantiations of TeacherCopilot and StudentCopilotLight
old_teacher_copilot_inst = """      /*#__PURE__*/React.createElement(TeacherCopilot, {
        analytics: analytics,
        roster: roster,
        tasks: tasks,
        sessionStatus: sessionStatus,
        sessionControl: sessionControl,
        setPage: setPage,
        tourMessage: tourMessage,
        setForceTour: setForceTour,
        profilePhoto: profilePhoto
      }),"""

new_teacher_copilot_inst = """      /*#__PURE__*/React.createElement(TeacherCopilot, {
        analytics: analytics,
        roster: roster,
        tasks: tasks,
        sessionStatus: sessionStatus,
        sessionControl: sessionControl,
        setPage: setPage,
        tourMessage: tourMessage,
        setForceTour: setForceTour,
        profilePhoto: profilePhoto,
        sessionCode: sessionCode
      }),"""

old_student_copilot_inst = """        // AI Copilot
        React.createElement(StudentCopilotLight, {
          currentTask, submitted, result, answeredCount, correctCount, selected, shortAnswer, timeSpent,
          studentPhoto, studentName
        })"""

new_student_copilot_inst = """        // AI Copilot
        React.createElement(StudentCopilotLight, {
          currentTask, submitted, result, answeredCount, correctCount, selected, shortAnswer, timeSpent,
          studentPhoto, studentName,
          sessionCode: sessionCode,
          studentId: studentId
        })"""

def replace_exact(old_code, new_code):
    global content
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("Replaced one block successfully.")
    else:
        # Standardize CRLF and spaces to check
        norm_old = old_code.replace("\r\n", "\n").strip()
        norm_content = content.replace("\r\n", "\n")
        if norm_old in norm_content:
            content = norm_content.replace(norm_old, new_code.replace("\r\n", "\n"))
            print("Replaced one block successfully after CRLF normalization.")
        else:
            print("Could not find block to replace.")

replace_exact(old_teacher_copilot_start, new_teacher_copilot_start)
replace_exact(old_teacher_call_ai, new_teacher_call_ai)
replace_exact(old_student_copilot_start, new_student_copilot_start)
replace_exact(old_student_call_ai, new_student_call_ai)
replace_exact(old_teacher_copilot_inst, new_teacher_copilot_inst)
replace_exact(old_student_copilot_inst, new_student_copilot_inst)

with open(vyom_html_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Copilot code integration completed.")
