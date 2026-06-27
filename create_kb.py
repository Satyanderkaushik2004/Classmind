import os

# Create knowledge_base folder if it does not exist
kb_dir = r"c:\Users\ADMIN\Downloads\Classmind-main\knowledge_base"
os.makedirs(kb_dir, exist_ok=True)

docs = {
    "teacher_dashboard": {
        "title": "Teacher Dashboard",
        "does": "Serves as the main control center for instructors to manage active class sessions, push questions, view attendance in real-time, monitor student understanding, and review raised doubts.",
        "why": "It centralizes live class interactions, enabling teachers to quickly adjust their instruction and keep students engaged without shuffling between multiple tools.",
        "when": "Used continuously during a live class session, as well as before starting a class to prepare materials.",
        "how": "1. Log into your VYOM teacher account.\n2. Click 'Create Class Session' and enter a topic and duration.\n3. Share the 6-digit session code with students.\n4. Once students join, use the main dashboard panels to send tasks, resolve doubts, and view real-time participation metrics.",
        "best": "Keep the dashboard open on a secondary monitor if possible so you can monitor student status while presenting slides or code.",
        "mistakes": "Forgetting to officially end the session using the 'End Class' button, which keeps the session status open and postpones reports compilation.",
        "trouble": "If metrics are not updating, verify your internet connection or check the WebSocket connection indicator at the top of the dashboard. Refresh if disconnected.",
        "related": "Session Management, Tasks, Attendance, Chat & Doubt System"
    },
    "student_dashboard": {
        "title": "Student Dashboard",
        "does": "Provides a clean, real-time portal for students to receive active tasks, write and run code in the coding lab, submit responses, view the leaderboard, raise hands, and chat.",
        "why": "It creates an interactive, focused learning environment for students to participate in live classroom activities.",
        "when": "Used by students during live class sessions to interact and submit work.",
        "how": "1. Go to the student login portal.\n2. Enter the 6-digit session code provided by the teacher and enter your name.\n3. Click 'Join as Student' and wait in the Waiting Room if the session has not started yet.\n4. When live, view and complete tasks as they are sent by the teacher.",
        "best": "Use a desktop or laptop browser when working on coding tasks to have optimal editor space.",
        "mistakes": "Closing the browser tab or navigating away during a locked test, which triggers cheating warnings on the teacher's dashboard.",
        "trouble": "If tasks do not appear, ensure you are not suspended or check the WebSocket status at the bottom of the screen.",
        "related": "Coding Lab, Tests, Tasks, Chat & Doubt System"
    },
    "ai_insights": {
        "title": "AI Insights",
        "does": "Analyzes classroom performance, participation levels, and task answers to automatically identify common mistakes, topic confusion, and students at risk of falling behind.",
        "why": "It reduces the cognitive load on teachers by transforming raw data into actionable educational advice during and after class.",
        "when": "Review during class pause points or after ending the session.",
        "how": "1. Open the Teacher Dashboard.\n2. Scroll to the AI Insights card or navigate to the Analytics tab.\n3. Review the automatically generated summaries of topic confusion and at-risk students.",
        "best": "Use the insights post-session to plan remedial activities or target specific students in the next class.",
        "mistakes": "Assuming the insights are absolute; they should be combined with the teacher's personal observation and pedagogy.",
        "trouble": "If insights are empty, ensure students have submitted answers to at least one task or quiz so there is data to analyze.",
        "related": "Real-Time Insights, Reports, Student Performance"
    },
    "teaching_intelligence": {
        "title": "Teaching Intelligence",
        "does": "Empowers teachers with smart, automated classroom interventions, recommending when to pause, pivot topics, trigger a quick poll, or group students based on performance.",
        "why": "It guides teachers with real-time pedagogical recommendations to improve student learning outcomes.",
        "when": "Used during live sessions when student understanding drops or participation flag warnings trigger.",
        "how": "1. Look at the top alert panel on the Teacher Dashboard.\n2. When understanding drops below 50%, a 'Teaching Intelligence Suggestion' will trigger.\n3. Click the suggestion to execute the recommended action (e.g. explain key concept, send a simplified hint, or create student groups).",
        "best": "Respond proactively to intelligence prompts to keep the class average above the understanding threshold.",
        "mistakes": "Ignoring warnings when the class average is low, leading to snowballing confusion.",
        "trouble": "If intelligence warnings are not appearing, check settings to ensure educational alerts are enabled.",
        "related": "AI Insights, Classroom Controls"
    },
    "lesson_planner": {
        "title": "Lesson Planner",
        "does": "Generates complete, structured lesson plans including curriculum objectives, warm-up exercises, core concepts, activities, timings, and assessments based on topic and grade level.",
        "why": "It saves hours of preparation time for teachers by generating high-quality curricula structures.",
        "when": "Used before starting a class session to plan the curriculum.",
        "how": "1. Navigate to the Lesson Planner page from the side menu.\n2. Enter the subject, target grade, chapter, and topic.\n3. Select a template and click 'Generate Lesson Plan'.\n4. Edit sections or export the plan to PDF/Word.",
        "best": "Add custom constraints (e.g. 'include a coding challenge' or 'focus on interactive analogies') to tailor the generated plan.",
        "mistakes": "Generating plans that are too long for the allocated class time without reviewing individual section timings.",
        "trouble": "If generation fails, verify that your server-side GEMINI_API_KEY or OPENROUTER_API_KEY is configured correctly.",
        "related": "Content Hub, Tasks"
    },
    "ai_replay": {
        "title": "AI Replay",
        "does": "Allows teachers to replay a completed classroom session, walking through the timeline of when tasks were sent, how understanding fluctuated, and when doubts were raised.",
        "why": "It helps teachers reflect on their teaching pace, question difficulty, and student engagement patterns.",
        "when": "Used after a session has ended for reflection and auditing.",
        "how": "1. Go to the Sessions tab from the teacher account.\n2. Find a previous completed session and click 'AI Replay'.\n3. Slide the timeline control to see class metrics at any minute of the session.",
        "best": "Use the replay to trace the exact moment students started struggling with a topic to improve task design.",
        "mistakes": "Overlooking the correlation between participation peaks and active tasks.",
        "trouble": "If replay is unavailable, the session might not have been closed using the 'End Class' button properly, or it had zero tasks.",
        "related": "Reports, Analytics"
    },
    "content_hub": {
        "title": "Content Hub",
        "does": "Acts as a repository for classroom learning materials, enabling teachers to upload documents, slide decks, and code files which are instantly made available to students.",
        "why": "It centralizes files sharing so students can view relevant documents directly inside their student portal.",
        "when": "Used before or during class to distribute readings, worksheets, or guidelines.",
        "how": "1. Navigate to the Content Hub tab.\n2. Drag and drop your files (PDF, images, text, json) or click to upload.\n3. The platform will automatically generate smart learning objectives and descriptions for each file.\n4. Students can view or download files from their content dashboard.",
        "best": "Upload worksheets and slides before starting the live session to minimize interruptions.",
        "mistakes": "Uploading massive files (over 50MB) that can slow down loading times for students on slower connections.",
        "trouble": "If a file is not visible to students, ensure the file is successfully uploaded and check its metadata status.",
        "related": "Content Upload, Google Drive Integration"
    },
    "attendance": {
        "title": "Attendance Tracking",
        "does": "Automatically monitors and records the entry and exit times of every student joining the session, generating a live presence registry.",
        "why": "It automates roll-calling, saving valuable instructional time and ensuring accurate participation records.",
        "when": "Monitored live during class and exported upon session end.",
        "how": "1. Access the Attendance tab on the Teacher Dashboard.\n2. View the live table of connected students, their join times, status (Active/Away), and elapsed time.\n3. Click 'Export PDF' to download the completed attendance registry.",
        "best": "Cross-reference attendance records with participation percentages to detect disengaged students who joined but did not answer tasks.",
        "mistakes": "Closing the teacher server before students leave, which can result in missing leave times.",
        "trouble": "If a student joined but is not in the attendance list, verify they entered the correct 6-digit session code.",
        "related": "Live Attendance, Session Management"
    },
    "reports": {
        "title": "Session Reports",
        "does": "Generates comprehensive, professional reports summarizing class performance, individual student scores, attendance logs, and question analysis.",
        "why": "It provides formal records that can be shared with school administration, parents, or saved for grading purposes.",
        "when": "Generated automatically after a session ends.",
        "how": "1. Navigate to the Reports section.\n2. Choose a completed session from the list.\n3. Review the overview metrics (average score, pass rate, active time).\n4. Click 'Download PDF' or 'Export Excel' to download the file.",
        "best": "Set up Google Drive integration so reports are automatically synced to your cloud drive upon session end.",
        "mistakes": "Trying to download reports of active sessions; the session must be ended to complete reporting calculations.",
        "trouble": "If PDF report generation fails, ensure the ReportLab library is working on your server.",
        "related": "Student Reports, Performance Reports, Export Features"
    },
    "analytics": {
        "title": "Classroom Analytics",
        "does": "Provides deep statistical breakdowns of student progress, option frequency heatmaps for MCQs, error distributions, and code compilation metrics.",
        "why": "It transforms raw student responses into visual graphs and tables, highlighting learning gaps and instructional efficacy.",
        "when": "Reviewed during lesson milestones and at the end of class.",
        "how": "1. Navigate to the Analytics tab on the dashboard.\n2. Inspect the bar charts, line graphs, and pie charts representing classroom metrics.\n3. Click any task to see option details, correct response ratios, and student response lists.",
        "best": "Analyze the wrong option distribution on MCQ tasks to identify common misconceptions.",
        "mistakes": "Ignoring code compilation failure rates in the coding analysis panel, which points to syntax challenges.",
        "trouble": "If the charts do not load, verify that Chart.js is properly loaded in the browser console.",
        "related": "Classroom Analytics, Student Performance"
    },
    "student_performance": {
        "title": "Student Performance",
        "does": "Tracks and benchmarks individual student metrics across tasks, quizzes, coding problems, response speed, and overall accuracy.",
        "why": "It helps teachers identify specific students who need one-on-one help and recognize top performers.",
        "when": "Used to monitor student scores and identify struggling individuals during class.",
        "how": "1. Click 'Students' or 'Roster' on the dashboard.\n2. Click a student's name to view their performance card.\n3. Inspect their task completion rate, average score, compilation history, and raised hands.",
        "best": "Review the performance profiles weekly to track growth trends over multiple sessions.",
        "mistakes": "Evaluating students solely on speed; focus on accuracy and completion quality.",
        "trouble": "If a student's performance data seems out of date, verify that their submissions were marked as graded.",
        "related": "AI Insights, Analytics, Student Reports"
    },
    "coding_lab": {
        "title": "Coding Lab",
        "does": "Embedded programming sandbox supporting multi-language compilation (Python, JavaScript, Java, C++, C, Go) with real-time test case verification.",
        "why": "It enables computer science teachers to assign programming problems and automatically verify student code correctness.",
        "when": "Used when teaching programming, algorithm design, or software engineering concepts.",
        "how": "1. Create a coding task with problem statement, starter code, and test cases.\n2. Push the task to students.\n3. Students write code in the embedded editor, compile, and run.\n4. Code is auto-graded against hidden/visible test cases, and results are reported to the teacher.",
        "best": "Provide clear starter code and define robust test cases checking both basic logic and edge cases.",
        "mistakes": "Not checking language syntax in the starter code, which causes student compilation errors immediately.",
        "trouble": "If student code fails to run, check sandbox server resources or ensure the sandbox service is running on the backend.",
        "related": "Tasks, Student Dashboard"
    },
    "tests": {
        "title": "Tests Mode",
        "does": "Initiates a formal, timed assessment environment where browser tabs are monitored, anti-cheat limits are active, and navigation is restricted.",
        "why": "It provides a secure, high-integrity environment for classroom examinations and quizzes.",
        "when": "Used for graded exams, weekly quizzes, or formal evaluations.",
        "how": "1. Go to the Tests tab.\n2. Set up the questions, duration, and cheating tolerance thresholds.\n3. Click 'Start Test'.\n4. Monitor live student progress and cheat warnings in real-time. Click 'End Test' to conclude and lock all inputs.",
        "best": "Warn students before the test about the anti-cheat warning triggers to minimize accidental tab switching.",
        "mistakes": "Leaving tests open indefinitely without setting an automatic time limit.",
        "trouble": "If a student is locked out due to cheat warnings, the teacher can unlock them manually from the student control panel.",
        "related": "Tasks, Classroom Controls"
    },
    "tasks": {
        "title": "Tasks Management",
        "does": "Enables creation, scheduling, editing, and distribution of learning tasks (MCQs, Short Answer, Long Answer, Coding Challenges) to the classroom.",
        "why": "It acts as the primary tool for active learning, turning passive lecturing into interactive training.",
        "when": "Used before class to queue questions and during class to distribute them.",
        "how": "1. Navigate to the Tasks tab.\n2. Click 'Create Task' and choose the question type.\n3. Enter details, options, correct answers, and hints.\n4. Click 'Assign Task' to push it immediately, or save it to the session queue.",
        "best": "Prepare a mixture of easy MCQs for checks-for-understanding and harder coding/short-answer challenges for group work.",
        "mistakes": "Forgetting to set a correct answer for MCQs, which breaks automated grading.",
        "trouble": "If students complain they cannot see a task, ensure the task state is set to 'Active' or 'Sent' and not 'Draft'.",
        "related": "Coding Lab, Student Dashboard"
    },
    "classroom_controls": {
        "title": "Classroom Controls",
        "does": "Provides master buttons to control the classroom session state, including starting, pausing, resuming, and ending the live class, as well as toggling student chat access.",
        "why": "It gives teachers complete command over the flow of the class, preventing students from answering questions or chatting when they should be listening.",
        "when": "Used throughout the live session to transition between teaching modes.",
        "how": "1. Locate the control bar at the top of the Teacher Dashboard.\n2. Click 'Pause Session' to freeze student screens.\n3. Click 'Toggle Chat' to lock/unlock the global classroom chat.\n4. Click 'End Session' when the class has completed.",
        "best": "Pause the session when explaining a complex slide to ensure students' attention is focused on you, not on their task editors.",
        "mistakes": "Pausing the session while students are mid-coding, which interrupts their editor typing and could lose progress.",
        "trouble": "If controls do not respond, refresh the teacher dashboard to re-establish the socket connection.",
        "related": "Session Management, Waiting Room"
    },
    "waiting_room": {
        "title": "Waiting Room",
        "does": "Holds students in a secure pre-class queue before the teacher officially launches the live session. Shows student photos, admission requests, and plays a preparation video.",
        "why": "It prevents students from accessing classroom features until the teacher is ready to moderate and teach.",
        "when": "Active between session creation and the official 'Start Session' action.",
        "how": "1. Create a session to generate the 6-digit code.\n2. Students who join using this code will enter the Waiting Room.\n3. Review student photos and names in the queue.\n4. Click 'Approve' to admit them or 'Reject' to deny entry.\n5. Click 'Start Session' to go live and move everyone to the dashboard.",
        "best": "Enable 'Auto-Join' in settings if you want to skip manual approval for pre-registered students.",
        "mistakes": "Leaving students in the waiting room for long periods without starting the session.",
        "trouble": "If students cannot connect to the waiting room, check if the session code was typed correctly.",
        "related": "Classroom Controls, Session Management"
    },
    "notifications": {
        "title": "Notification System",
        "does": "Dispatches real-time alerts, emails, and platform toasts to teachers and students regarding session actions, hand raises, cheat warnings, and report syncs.",
        "why": "It keeps all classroom participants informed of important events instantly.",
        "when": "Runs in the background during active sessions.",
        "how": "1. Go to Profile Settings -> Notifications.\n2. Toggle email or desktop notifications for different categories (e.g. Cheat Alerts, Doubt Submissions, Attendance Updates).\n3. Save configuration preferences.",
        "best": "Keep cheat alerts enabled on your desktop so you are immediately notified if a student leaves a test.",
        "mistakes": "Disabling all notifications, leading to missed doubt submissions and student hand raises.",
        "trouble": "If email notifications are not arriving, check your spam folder or verify SMTP credentials in the server configurations.",
        "related": "Profile Settings, Chat & Doubt System"
    },
    "profile_settings": {
        "title": "Profile Settings",
        "does": "Allows users to update their personal details, profile photos, display names, platform language, visual themes, and external cloud integrations.",
        "why": "It provides a personalized workspace, localization controls, and account security management.",
        "when": "Accessed anytime from the top-right user menu.",
        "how": "1. Click on your profile photo in the top right and select 'Profile Settings'.\n2. Update fields like Name, Email, Theme, and Language.\n3. Link your Google Drive account for automatic report exports.\n4. Click 'Save Changes' to update profiles.",
        "best": "Upload a professional profile photo so students can identify their teacher easily in the Waiting Room and Chat.",
        "mistakes": "Forgetting to click 'Save Changes' before navigating away from the settings panel.",
        "trouble": "If Google Drive authentication fails, verify your browser is not blocking popups or check client ID settings.",
        "related": "Theme Settings, Language Settings, Google Drive Integration"
    },
    "theme_settings": {
        "title": "Theme Settings",
        "does": "Provides visual style customizers (Dark Mode, Light Mode, System Theme matching) and custom color accents to adjust the VYOM UI aesthetic.",
        "why": "It allows teachers and students to customize their workspace for comfort, accessibility, and visual preferences.",
        "when": "Accessed from profile settings or the theme selector widget.",
        "how": "1. Open Profile Settings or click the theme icon on the header.\n2. Choose between 'Dark', 'Light', or 'System' theme.\n3. Select a color accent (e.g. VYOM Orange, Deep Violet, Royal Blue).\n4. UI colors will transition immediately.",
        "best": "Use Dark theme in low-light environments to reduce eye strain, and choose high-contrast accents for accessibility.",
        "mistakes": "Selecting low-contrast color combinations that make text hard to read.",
        "trouble": "If the theme does not persist after reloading, check if cookies or localStorage are disabled in your browser.",
        "related": "Profile Settings"
    },
    "language_settings": {
        "title": "Language Settings",
        "does": "Manages platform localization, enabling instant, dynamic runtime translation of all UI text, labels, forms, charts, and AI chatbot responses.",
        "why": "It supports internationalization (i18n), making the VYOM educational platform accessible to non-English speaking teachers and students.",
        "when": "Configured at initial setup or changed mid-session via settings.",
        "how": "1. Open the language settings menu.\n2. Select your language (e.g., Hindi, Punjabi, Marathi, Chinese, English).\n3. The platform will translate all elements immediately without requiring a page reload.",
        "best": "Choose the platform language matching your students' instruction medium to ensure consistent teaching terms.",
        "mistakes": "Assuming language switching requires a page refresh, which could sever active WebSocket sessions.",
        "trouble": "If certain dynamic texts remain in English, check that the translations registry contains the corresponding key.",
        "related": "Profile Settings, Multilingual Support"
    },
    "session_management": {
        "title": "Session Management",
        "does": "Governs the lifecycle of a class session from initialization, student registration, state changes (waiting, active, paused, ended), to cleanup and database persistence.",
        "why": "It secures classroom data, manages student connections, and guarantees state continuity across network reconnects.",
        "when": "Active from the creation of the class until its reports are saved.",
        "how": "1. Teacher clicks 'Create Class Session' to instantiate session states.\n2. Server assigns a unique 6-digit code.\n3. Manage the active session via classroom controls.\n4. End the session to archive data and compile grading reports.",
        "best": "Avoid running multiple active sessions simultaneously under a single teacher account to prevent socket collision.",
        "mistakes": "Closing the teacher server window instead of ending the session, which leaves session memory in an uncompiled state.",
        "trouble": "If a session code is reported as expired, check the session registry or create a new session.",
        "related": "Classroom Controls, Waiting Room"
    },
    "classroom_analytics": {
        "title": "Classroom Analytics",
        "does": "Gathers and visualizes real-time performance analytics including response distributions, time-per-question, accuracy trends, and overall understanding rates.",
        "why": "It provides instant feedback, helping teachers identify if a topic requires immediate explanation.",
        "when": "Consulted constantly during active task execution.",
        "how": "1. Open the analytics view on the Teacher Dashboard.\n2. Inspect the accuracy gauges and student answering feeds.\n3. Toggle charts to view summaries across various task types.",
        "best": "Review the topic confusion metrics during group activities to formulate focused interventions.",
        "mistakes": "Assuming low understanding is always an issue; check if the task has a high difficulty level.",
        "trouble": "If data is missing from the charts, ensure the tasks have been sent to and submitted by the students.",
        "related": "Analytics, Reports"
    },
    "google_drive_integration": {
        "title": "Google Drive Integration",
        "does": "Connects the teacher's profile to Google Drive, automatically exporting and uploading session reports and excel sheets to a dedicated 'VYOM Reports' folder.",
        "why": "It automates report backups, making them accessible outside the platform and easy to share with school directors.",
        "when": "Configured once in profile settings and runs automatically upon ending sessions.",
        "how": "1. Go to Profile Settings -> API & Integrations.\n2. Click 'Connect Google Drive' and authenticate through Google OAuth.\n3. Upon successful integration, a folder named 'VYOM Reports' will be created.\n4. Close session, and reports will auto-sync.",
        "best": "Verify your Google account has enough storage space to host reports and spreadsheets.",
        "mistakes": "Disconnecting the integration during an active session, which prevents the auto-upload trigger on class end.",
        "trouble": "If reports are not syncing, check Google Drive connection status in profile settings or re-authorize.",
        "related": "Profile Settings, Reports"
    },
    "content_upload": {
        "title": "Content Upload",
        "does": "Enables teachers to upload classroom documents, spreadsheets, slides, and images, automatically triggering AI metadata generation (objectives, summaries).",
        "why": "It simplifies content distribution and structures document metadata automatically.",
        "when": "Used when preparing files in the Content Hub.",
        "how": "1. Open the Content Hub.\n2. Drag and drop file attachments or click 'Upload File'.\n3. Wait for the server to process the file and generate learning objectives.\n4. View files on student portals.",
        "best": "Upload PDFs and images instead of raw text files for better formatting in student portals.",
        "mistakes": "Uploading unsupported file formats, which can result in metadata parsing failures.",
        "trouble": "If upload fails, check if the file size exceeds server limits or verify write permissions in the data folder.",
        "related": "Content Hub, Google Drive Integration"
    },
    "export_features": {
        "title": "Export Features",
        "does": "Allows downloading classroom data including grades, attendance logs, and analytical reports in PDF and Microsoft Excel formats.",
        "why": "It supports offline grading, printing, archiving, and integration with external school databases.",
        "when": "Used after class completion or when downloading mid-session rosters.",
        "how": "1. Navigate to the Reports or Attendance tab.\n2. Click 'Export PDF' or 'Export Excel'.\n3. The server compiles the files and triggers a local browser download.",
        "best": "Export Excel sheets for grade calculations and PDF formats for printing/sharing.",
        "mistakes": "Opening exported spreadsheets in legacy excel viewers that don't support modern xlsx formats.",
        "trouble": "If Excel generation fails, verify the openpyxl library is installed on the Python server.",
        "related": "Reports, Attendance Tracking"
    },
    "chat_doubt_system": {
        "title": "Chat & Doubt System",
        "does": "Integrates a double-channel communication system: a live global classroom chat for peer discussion and a private Doubt Queue for students to submit questions to the teacher.",
        "why": "It facilitates classroom communication and allows students to ask questions privately without interrupting the lecture.",
        "when": "Active during live sessions.",
        "how": "1. Students click 'Submit Doubt' on their dashboard, entering a query and optional screenshot.\n2. Teacher receives a sound alert and a badge on the 'Doubts' panel.\n3. Teacher reviews the doubt, explains it, and clicks 'Resolve Doubt' to update status.\n4. Live Chat can be paused using the chat toggle switch.",
        "best": "Encourage students to submit doubts through the queue rather than flood the global chat room.",
        "mistakes": "Leaving unresolved doubts on the queue when ending the session.",
        "trouble": "If chat messages are not delivering, check the WebSocket connection status on the dashboard header.",
        "related": "Classroom Controls, Notifications"
    },
    "student_reports": {
        "title": "Student Reports",
        "does": "Generates individual diagnostic scorecards detailing a student's accuracy, participation rate, response speed, and coding solutions.",
        "why": "It provides students and parents with personalized feedback highlighting strengths and specific topics needing study.",
        "when": "Shared with students after class or during parent-teacher conferences.",
        "how": "1. Go to the student performance roster.\n2. Select a student and click 'Generate Report'.\n3. Click 'Email Report' to send it directly to their registered email or export it.",
        "best": "Email reports automatically at the end of every week to maintain parent feedback loops.",
        "mistakes": "Sending student reports containing blank entries due to student absences during the session.",
        "trouble": "If report emails are bounced, verify SMTP settings and check that the student's email address is formatted correctly.",
        "related": "Reports, Student Performance"
    },
    "performance_reports": {
        "title": "Performance Reports",
        "does": "Compiles class-wide performance metrics, ranking student scores, average response speed, task completion rate, and curriculum success percentages.",
        "why": "It gives teachers a macro-level view of class achievements and points to learning trends.",
        "when": "Consulted by school admins and teachers after grading milestones.",
        "how": "1. Open the Reports section.\n2. Click on 'Performance Summary' or 'Gradebook'.\n3. Filter by session, task difficulty, or date range.",
        "best": "Use the gradebook view to export compiled averages directly into your school's official registry.",
        "mistakes": "Failing to check class averages before moving to a new syllabus topic.",
        "trouble": "If data is missing, ensure the tests or tasks have been graded by the system.",
        "related": "Reports, Analytics"
    },
    "live_attendance": {
        "title": "Live Attendance",
        "does": "Shows real-time indicators of which students are active, away, offline, or requesting entry, updating instantly via WebSockets.",
        "why": "It helps teachers detect when a student is disengaged, has disconnected, or has minimized their browser window.",
        "when": "Visible on the teacher dashboard roster during active classes.",
        "how": "1. Open the Roster panel on the dashboard.\n2. Observe status indicator lights next to student names (Green = Active, Orange = Away, Red = Offline).\n3. Click 'Refresh Roster' to manually force a status update if needed.",
        "best": "Keep an eye on the away count; if it rises, prompt the class with an interactive task to capture their attention.",
        "mistakes": "Assuming a student is cutting class because their status turns Red briefly due to network latency.",
        "trouble": "If student status lights are not changing, check if the WebSocket channel is active.",
        "related": "Attendance Tracking, Classroom Controls"
    },
    "real_time_insights": {
        "title": "Real-Time Insights",
        "does": "Generates instantaneous alerts on teacher screens regarding student confusion zones, task completion speeds, and sudden performance drops.",
        "why": "It allows teachers to pivot their lecture topics immediately in response to student difficulties.",
        "when": "Monitored during lecture slides and active tasks.",
        "how": "1. Look at the 'Real-Time Insights' panel on the teacher view.\n2. Read notifications like '5 students failed Task 2 within 30 seconds' or 'Confusion detected on recursion'.\n3. Take immediate corrective action.",
        "best": "Use these insights to address class-wide errors before moving to independent student work.",
        "mistakes": "Addressing errors only at the end of class, after student confusion has compounded.",
        "trouble": "If real-time alerts are not showing, ensure your notification dashboard settings are checked.",
        "related": "AI Insights, Classroom Analytics"
    }
}

for name, content in docs.items():
    file_path = os.path.join(kb_dir, f"{name}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# {content['title']}\n\n")
        f.write(f"## What it does\n{content['does']}\n\n")
        f.write(f"## Why it exists\n{content['why']}\n\n")
        f.write(f"## When it should be used\n{content['when']}\n\n")
        f.write(f"## How to use it\n{content['how']}\n\n")
        f.write(f"## Best practices\n{content['best']}\n\n")
        f.write(f"## Common mistakes\n{content['mistakes']}\n\n")
        f.write(f"## Troubleshooting steps\n{content['trouble']}\n\n")
        f.write(f"## Related features\n{content['related']}\n")
    print(f"Created {name}.md")

print("All 30 knowledge base files populated successfully!")
