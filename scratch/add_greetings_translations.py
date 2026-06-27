import json
import os

loc_dir = r"c:\Users\ADMIN\Downloads\Classmind-main\localization"

greetings_trans = {
    "hi": {
        "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.": "👋 हे! मैं आपका **व्योम एआई शिक्षण सहायक** हूँ। अपनी कक्षा के बारे में मुझसे कुछ भी पूछें, सामग्री तैयार करें, या प्लेटफ़ॉर्म सहायता प्राप्त करें।",
        "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.": "🧠 वापस स्वागत है! मैं आपका एआई सह-शिक्षक हूँ — आपकी कक्षा का विश्लेषण करने, प्रश्न बनाने, सुविधाओं को समझाने, या किसी भी विषय में मदद करने के लिए तैयार हूँ।",
        "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!": "✨ नमस्कार! मैं आपका व्योम शिक्षण सहायक हूँ। मुझसे एमसीक्यू (MCQ) बनाने, अपने सत्र का सारांश देने, किसी अवधारणा को समझाने, या किसी भी सुविधा के बारे में मार्गदर्शन करने के लिए कहें!"
    },
    "pa": {
        "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.": "👋 ਹੇ! ਮੈਂ ਤੁਹਾਡਾ **ਵਿਓਮ ਏਆਈ ਅਧਿਆਪਨ ਸਹਾਇਕ** ਹਾਂ। ਆਪਣੀ ਕਲਾਸ ਬਾਰੇ ਮੈਨੂੰ ਕੁਝ ਵੀ ਪੁੱਛੋ, ਸਮੱਗਰੀ ਤਿਆਰ ਕਰੋ, ਜਾਂ ਪਲੇਟਫਾਰਮ ਸਹਾਇਤਾ ਪ੍ਰਾਪਤ ਕਰੋ।",
        "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.": "🧠 ਜੀ ਆਇਆਂ ਨੂੰ! ਮੈਂ ਤੁਹਾਡਾ ਏਆਈ ਸਹਿ-ਅਧਿਆਪਕ ਹਾਂ — ਤੁਹਾਡੀ ਕਲਾਸ ਦਾ ਵਿਸ਼ਲੇਸ਼ਣ ਕਰਨ, ਸਵਾਲ ਬਣਾਉਣ, ਵਿਸ਼ੇਸ਼ਤਾਵਾਂ ਦੀ ਵਿਆਖਿਆ ਕਰਨ, ਜਾਂ ਕਿਸੇ ਵੀ ਵਿਸ਼ੇ ਵਿੱਚ ਮਦਦ ਕਰਨ ਲਈ ਤਿਆਰ ਹਾਂ।",
        "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!": "✨ ਨਮਸਕਾਰ! ਮੈਂ ਤੁਹਾਡਾ ਵਿਓਮ ਅਧਿਆਪਨ ਸਹਾਇਕ ਹਾਂ। ਮੈਨੂੰ ਐਮਸੀਕਿਊ (MCQ) ਬਣਾਉਣ, ਆਪਣੇ ਸੈਸ਼ਨ ਦਾ ਸਾਰ ਦੇਣ, ਕਿਸੇ ਸੰਕਲਪ ਦੀ ਵਿਆਖਿਆ ਕਰਨ, ਜਾਂ ਕਿਸੇ ਵੀ ਵਿਸ਼ੇਸ਼ਤਾ ਬਾਰੇ ਮਾਰਗਦਰਸ਼ਨ ਕਰਨ ਲਈ ਕਹੋ!"
    },
    "mr": {
        "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.": "👋 हे! मी तुमचा **व्योम एआय शिक्षण सहाय्यक** आहे. तुमच्या वर्गाबद्दल मला काहीही विचारा, शैक्षणिक सामग्री तयार करा किंवा प्लॅटफॉर्म मदत मिळवा.",
        "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.": "🧠 परत स्वागत आहे! मी तुमचा एआय सह-शिक्षक आहे — तुमच्या वर्गाचे विश्लेषण करण्यासाठी, प्रश्न तयार करण्यासाठी, वैशिष्ट्ये स्पष्ट करण्यासाठी किंवा कोणत्याही विषयात मदत करण्यासाठी तयार आहे.",
        "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!": "✨ नमस्कार! मी तुमचा व्योम शिक्षण सहाय्यक आहे. मला एमसीक्यू तयार करण्यास, तुमच्या सत्राचा सारांश देण्यास, एखादी संकल्पना स्पष्ट करण्यास किंवा कोणत्याही वैशिष्ट्याबद्दल मार्गदर्शन करण्यास सांगा!"
    },
    "zh": {
        "👋 Hey! I'm your **VYOM AI Teaching Assistant** — powered by Claude. Ask me anything about your class, generate content, or get platform help.": "👋 嘿！我是您的 **VYOM AI 教学助手**。您可以向我咨询关于课堂的任何问题、生成教学内容或获取平台帮助。",
        "🧠 Welcome back! I'm your AI co-teacher — ready to analyse your class, create questions, explain features, or help with any subject.": "🧠 欢迎回来！我是您的 AI 助教 — 随时为您分析班级、创建问题、解释功能或提供任何学科的帮助。",
        "✨ Hi there! I'm your VYOM Teaching Assistant. Ask me to generate MCQs, summarise your session, explain a concept, or guide you through any feature!": "✨ 嗨，您好！我是您的 VYOM 教学助手。您可以让我生成选择题、总结课程会话、解释概念或指导您使用任何功能！"
    }
}

for lang, greetings in greetings_trans.items():
    file_path = os.path.join(loc_dir, f"{lang}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Merge greetings
        for k, v in greetings.items():
            data[k] = v
            
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Updated greetings for {lang}")
