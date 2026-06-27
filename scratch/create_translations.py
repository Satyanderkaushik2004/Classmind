import os
import re
import json
import sys

vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"
loc_dir = r"c:\Users\ADMIN\Downloads\Classmind-main\localization"
os.makedirs(loc_dir, exist_ok=True)

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

match = re.search(r"const TRANSLATIONS = (\{.*?\n\s*\n\s*\});", content, re.DOTALL)
if not match:
    match = re.search(r"const TRANSLATIONS = (\{.*?\n\s*\});", content, re.DOTALL)

if not match:
    print("Could not locate TRANSLATIONS block in vyom.html")
    sys.exit(1)

translations_block = match.group(1)

hi_block_match = re.search(r"hi:\s*\{(.*?)\n\s*\}\s*,", translations_block, re.DOTALL)
pa_block_match = re.search(r"pa:\s*\{(.*?)\n\s*\}\s*$", translations_block, re.DOTALL)

if not hi_block_match or not pa_block_match:
    pa_block_match = re.search(r"pa:\s*\{(.*?)\n\s*\}", translations_block, re.DOTALL)

def parse_dict_lines(block_text):
    dict_res = {}
    pattern = r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"'
    matches = re.findall(pattern, block_text)
    for k, v in matches:
        # Convert JS unicode escapes like \uD83D into actual surrogate code characters
        k_uni = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), k)
        v_uni = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), v)
        
        # Combine UTF-16 surrogate pairs into single characters
        try:
            k_decoded = k_uni.encode('utf-16', 'surrogatepass').decode('utf-16')
        except Exception:
            k_decoded = k_uni
            
        try:
            v_decoded = v_uni.encode('utf-16', 'surrogatepass').decode('utf-16')
        except Exception:
            v_decoded = v_uni
            
        k_decoded = k_decoded.replace('\\"', '"').replace('\\n', '\n')
        v_decoded = v_decoded.replace('\\"', '"').replace('\\n', '\n')
        dict_res[k_decoded] = v_decoded
    return dict_res

hi_dict = parse_dict_lines(hi_block_match.group(1)) if hi_block_match else {}
pa_dict = parse_dict_lines(pa_block_match.group(1)) if pa_block_match else {}

print(f"Extracted {len(hi_dict)} Hindi translations and {len(pa_dict)} Punjabi translations.")

core_mr = {
    "Profile Settings": "प्रोफाईल सेटिंग्ज",
    "Manage your profile, preferences and account settings.": "तुमची प्रोफाईल, प्राधान्ये आणि खाते सेटिंग्ज व्यवस्थापित करा.",
    "View Public Profile": "सार्वजनिक प्रोफाईल पहा",
    "Sessions": "सत्र",
    "Students": "विद्यार्थी",
    "Participation": "सहभाग",
    "Understanding": "आकलन / समज",
    "Profile": "प्रोफाईल",
    "API & Integrations": "एपीआय आणि एकीकरण",
    "Preferences": "प्राधान्ये",
    "Manage notifications, localization and UI defaults.": "सूचना, स्थानिकीकरण आणि यूआय डीफॉल्ट व्यवस्थापित करा.",
    "Notification Preferences": "सूचना प्राधान्ये",
    "Manage how and when you receive system alerts.": "तुम्हाला सिस्टम अलर्ट कसे आणि कधी मिळतात ते व्यवस्थापित करा.",
    "System Alerts": "सिस्टम अलर्ट",
    "Language": "भाषा",
    "Choose your preferred platform language.": "तुमची पसंतीची प्लॅटफॉर्म भाषा निवडा.",
    "Timezone": "वेळ क्षेत्र",
    "Select your local classroom timezone.": "तुमचे स्थानिक वर्ग वेळ क्षेत्र निवडा.",
    "Account Actions": "खाते क्रिया",
    "Configure credentials, data export and status settings.": "क्रेडेंशियल, डेटा निर्यात आणि स्थिती सेटिंग्ज कॉन्फिगर करा.",
    "Change Password": "पासवर्ड बदला",
    "Update credentials security.": "क्रेडेंशियल सुरक्षा अद्यतनित करा.",
    "Delete Account": "खाते हटवा",
    "Permanently remove your account.": "तुमचे खाते कायमचे काढून टाका.",
    "English": "इंग्रजी",
    "Hindi": "हिंदी",
    "Punjabi": "पंजाबी",
    "Marathi": "मराठी",
    "Chinese (Simplified)": "चीनी (सरलीकृत)",
    "ANNOUNCEMENT": "घोषणा",
    "Language selector opened": "भाषा निवडक उघडले",
    "Active Tasks": "सक्रिय कार्ये",
    "Create Task": "कार्य तयार करा",
    "Task Title": "कार्याचे शीर्षक",
    "Task Description": "कार्याचे वर्णन",
    "Coding Question": "कोडिंग प्रश्न",
    "Multiple Choice": "बहुपर्यायी",
    "Assign Task": "कार्य सोपवा",
    "Submit Code": "कोड सबमिट करा",
    "Run Code": "कोड चालवा",
    "Test Cases": "चाचणी प्रकरणे",
    "Passed": "उत्तीर्ण",
    "Failed": "अपयशी",
    "Save": "जतन करा",
    "Cancel": "रद्द करा",
    "Close": "बंद करा",
    "Confirm": "पुष्टी करा",
    "Success": "यश",
    "Error": "त्रुटी",
    "Warning": "इशारा",
    "Info": "माहिती",
    "Save Changes": "बदल जतन करा",
    "Teacher Login": "शिक्षक लॉगिन",
    "Student Login": "विद्यार्थी लॉगिन",
    "Enter code...": "कोड प्रविष्ट करा...",
    "Enter name...": "नाव प्रविष्ट करा...",
    "Join as Student": "विद्यार्थी म्हणून सामील व्हा",
    "Create Class Session": "वर्ग सत्र तयार करा",
    "Enter class topic...": "वर्गाचा विषय प्रविष्ट करा...",
    "Duration": "कालावधी",
    "minutes": "मिनिटे",
    "Generate Code & Launch": "कोड जनरेट करा आणि लाँच करा",
    "Start Session": "सत्र सुरू करा",
    "Default Language:": "डीफॉल्ट भाषा:",
    "AI Assistant": "एआय सहाय्यक",
    "Ask VYOM anything about the classroom...": "वर्गाबद्दल व्योमला काहीही विचारा...",
    "Type a message...": "संदेश टाईप करा...",
    "Send": "पाठवा",
    "Export Excel": "एक्सेल निर्यात करा",
    "Export PDF": "पीडीएफ निर्यात करा",
    "Student Reports": "विद्यार्थी अहवाल",
    "Performance Summary": "कामगिरीचा सारांश",
    "Gradebook": "ग्रेडबुक",
    "No students connected yet. Start a session and I'll begin analyzing participation, engagement, and learning patterns in real-time.": "अद्याप कोणतेही विद्यार्थी कनेक्ट केलेले नाहीत. सत्र सुरू करा आणि मी रिअल-टाइममध्ये सहभाग, प्रतिबद्धता आणि शिकण्याच्या पद्धतींचे विश्लेषण करण्यास सुरवात करेन.",
    "Coding Lab — Multi-Language Sandbox": "कोडिंग लॅब — बहु-भाषा सँडबॉक्स",
    "Input (stdin)": "इनपुट (stdin)",
    "Output": "आउटपुट",
    "Console Output": "कंसोल आउटपुट",
    "Clear": "साफ करा",
    "Reset": "रीसेट करा",
    "Examples": "उदाहरणे",
    "Select Example": "उदाहरण निवडा",
    "Time Limit": "वेळ मर्यादा",
    "Submit Test": "चाचणी सबमिट करा",
    "Questions": "प्रश्न",
    "Score": "गुण",
    "Leaderboard": "लीडरबोर्ड",
    "Rank": "रँक",
    "Grade": "श्रेणी/ग्रेड",
    "Review": "पुनरावलोकन",
    "Pending Reviews": "प्रलंबित पुनरावलोकने",
    "Class Performance": "वर्गाची कामगिरी",
    "Average Score": "सरासरी गुण",
    "Passed Students": "उत्तीर्ण विद्यार्थी",
    "Theme:": "थीम:",
    "Language:": "भाषा:",
    "Create Test": "चाचणी तयार करा",
    "Start Test": "चाचणी सुरू करा",
    "Save Config": "कॉन्फिगरेशन जतन करा",
    "Settings": "सेटिंग्ज",
    "Classroom Analytics": "वर्ग विश्लेषण",
    "Topic Confusion": "विषय गोंधळ / संभ्रम",
    "At-Risk Students": "धोक्यात असलेले विद्यार्थी",
    "Doubt Queue": "शंका रांग",
    "Doubt Queue (Live)": "शंका रांग (थेट)",
    "No doubts raised yet.": "अद्याप कोणतीही शंका उपस्थित केलेली नाही.",
    "End Class": "वर्ग संपवा",
    "Pause Session": "सत्र थांबवा",
    "Resume Session": "सत्र पुन्हा सुरू करा",
    "Active Students": "सक्रिय विद्यार्थी",
    "Join via code": "कोडद्वारे सामील व्हा",
    "Waiting Room": "प्रतिक्षा कक्ष",
    "Live Attendance": "थेट उपस्थिती",
    "Real-Time Insights": "रिअल-टाइम अंतर्दृष्टी",
    "Lesson Planner": "पाठ नियोजक",
    "AI Replay": "एआय रीप्ले",
    "Content Hub": "सामग्री केंद्र",
    "Google Drive Integration": "गुगल ड्राइव्ह एकीकरण",
    "Export Features": "निर्यात वैशिष्ट्ये",
    "Chat & Doubt System": "चॅट आणि शंका प्रणाली",
    "Performance Reports": "कामगिरी अहवाल",
    "Teacher Dashboard": "शिक्षक डॅशबोर्ड",
    "Student Dashboard": "विद्यार्थी डॅशबोर्ड"
}

core_zh = {
    "Profile Settings": "个人设置",
    "Manage your profile, preferences and account settings.": "管理您的个人资料、偏好和账户设置。",
    "View Public Profile": "查看公开个人资料",
    "Sessions": "课堂会话",
    "Students": "学生",
    "Participation": "参与度",
    "Understanding": "理解度",
    "Profile": "个人资料",
    "API & Integrations": "API与集成",
    "Preferences": "偏好设置",
    "Manage notifications, localization and UI defaults.": "管理通知、本地化和用户界面默认值。",
    "Notification Preferences": "通知偏好",
    "Manage how and when you receive system alerts.": "管理您接收系统警报的方式和时间。",
    "System Alerts": "系统警报",
    "Language": "语言",
    "Choose your preferred platform language.": "选择您偏好的平台语言。",
    "Timezone": "时区",
    "Select your local classroom timezone.": "选择您本地的课堂时区。",
    "Account Actions": "账户操作",
    "Configure credentials, data export and status settings.": "配置凭据、数据导出和状态设置。",
    "Change Password": "修改密码",
    "Update credentials security.": "更新凭据安全。",
    "Delete Account": "注销账户",
    "Permanently remove your account.": "永久删除您的账户。",
    "English": "英文",
    "Hindi": "印地语",
    "Punjabi": "旁遮普语",
    "Marathi": "马拉地语",
    "Chinese (Simplified)": "中文 (简体)",
    "ANNOUNCEMENT": "公告",
    "Language selector opened": "语言选择器已打开",
    "Active Tasks": "活跃任务",
    "Create Task": "创建任务",
    "Task Title": "任务标题",
    "Task Description": "任务描述",
    "Coding Question": "编程题",
    "Multiple Choice": "选择题",
    "Assign Task": "分配任务",
    "Submit Code": "提交代码",
    "Run Code": "运行代码",
    "Test Cases": "测试用例",
    "Passed": "通过",
    "Failed": "失败",
    "Save": "保存",
    "Cancel": "取消",
    "Close": "关闭",
    "Confirm": "确认",
    "Success": "成功",
    "Error": "错误",
    "Warning": "警告",
    "Info": "信息",
    "Save Changes": "保存更改",
    "Teacher Login": "教师登录",
    "Student Login": "学生登录",
    "Enter code...": "输入代码...",
    "Enter name...": "输入姓名...",
    "Join as Student": "以学生身份加入",
    "Create Class Session": "创建课堂会话",
    "Enter class topic...": "输入课程主题...",
    "Duration": "时长",
    "minutes": "分钟",
    "Generate Code & Launch": "生成代码并启动",
    "Start Session": "开始课堂",
    "Default Language:": "默认语言：",
    "AI Assistant": "AI 助手",
    "Ask VYOM anything about the classroom...": "向 VYOM 咨询任何关于课堂的问题...",
    "Type a message...": "输入消息...",
    "Send": "发送",
    "Export Excel": "导出 Excel",
    "Export PDF": "导出 PDF",
    "Student Reports": "学生报告",
    "Performance Summary": "表现摘要",
    "Gradebook": "成绩册",
    "No students connected yet. Start a session and I'll begin analyzing participation, engagement, and learning patterns in real-time.": "尚未连接学生。启动会话，我将开始实时分析参与度、互动度和学习模式。",
    "Coding Lab — Multi-Language Sandbox": "编程实验室 — 多语言沙箱",
    "Input (stdin)": "输入 (stdin)",
    "Output": "输出",
    "Console Output": "控制台输出",
    "Clear": "清空",
    "Reset": "重置",
    "Examples": "示例",
    "Select Example": "选择示例",
    "Time Limit": "时间限制",
    "Submit Test": "提交测试",
    "Questions": "问题",
    "Score": "分数",
    "Leaderboard": "排行榜",
    "Rank": "排名",
    "Grade": "成绩",
    "Review": "审查",
    "Pending Reviews": "待审查",
    "Class Performance": "班级表现",
    "Average Score": "平均分",
    "Passed Students": "通过学生",
    "Theme:": "主题：",
    "Language:": "语言：",
    "Create Test": "创建测试",
    "Start Test": "开始测试",
    "Save Config": "保存配置",
    "Settings": "设置",
    "Classroom Analytics": "课堂分析",
    "Topic Confusion": "疑惑主题",
    "At-Risk Students": "预警学生",
    "Doubt Queue": "疑问队列",
    "Doubt Queue (Live)": "实时疑问队列",
    "No doubts raised yet.": "暂无提问。",
    "End Class": "结束课程",
    "Pause Session": "暂停课程",
    "Resume Session": "恢复课程",
    "Active Students": "在线学生",
    "Join via code": "通过代码加入",
    "Waiting Room": "等候室",
    "Live Attendance": "实时考勤",
    "Real-Time Insights": "实时洞察",
    "Lesson Planner": "课程计划生成器",
    "AI Replay": "AI 课程回放",
    "Content Hub": "资源中心",
    "Google Drive Integration": "谷歌云端硬盘集成",
    "Export Features": "导出功能",
    "Chat & Doubt System": "聊天和问答系统",
    "Performance Reports": "表现报告",
    "Teacher Dashboard": "教师控制台",
    "Student Dashboard": "学生端面板"
}

mr_dict = {**core_mr}
zh_dict = {**core_zh}

for key in hi_dict:
    if key not in mr_dict:
        mr_dict[key] = hi_dict[key]
    if key not in zh_dict:
        zh_dict[key] = key

with open(os.path.join(loc_dir, "hi.json"), "w", encoding="utf-8") as f:
    json.dump(hi_dict, f, ensure_ascii=False, indent=2)
with open(os.path.join(loc_dir, "pa.json"), "w", encoding="utf-8") as f:
    json.dump(pa_dict, f, ensure_ascii=False, indent=2)
with open(os.path.join(loc_dir, "mr.json"), "w", encoding="utf-8") as f:
    json.dump(mr_dict, f, ensure_ascii=False, indent=2)
with open(os.path.join(loc_dir, "zh.json"), "w", encoding="utf-8") as f:
    json.dump(zh_dict, f, ensure_ascii=False, indent=2)

print("Created JSON translation files successfully!")
