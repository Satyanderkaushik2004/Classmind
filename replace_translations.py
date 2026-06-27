vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

# Locate by direct string finding
start_marker = "const TRANSLATIONS = {"
end_marker = "const originalCreateElement = React.createElement;"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1:
    print("Could not find start marker: 'const TRANSLATIONS = {'")
elif end_idx == -1:
    print("Could not find end marker: 'const originalCreateElement = React.createElement;'")
else:
    replacement = """// ═════════════════════════════════════════════════════════════════
//  SCALABLE I18N LOCALIZATION SYSTEM (Part 1 — Manager & Loader)
// ═════════════════════════════════════════════════════════════════
class I18nManager {
  constructor() {
    this.registry = {
      en: {
        default: {}
      }
    };
    this.currentLanguage = localStorage.getItem('cm_lang') || 'en';
    this.fallbackLanguage = 'en';
    this.listeners = [];
    this.loadedLanguages = new Set(['en']);
    
    // Automatically load language pack for current language
    if (this.currentLanguage !== 'en') {
      this.loadLanguagePack(this.currentLanguage);
    }
  }

  subscribe(cb) {
    this.listeners.push(cb);
    return () => {
      this.listeners = this.listeners.filter(x => x !== cb);
    };
  }

  notify() {
    this.listeners.forEach(cb => { try { cb(this.currentLanguage); } catch(e) {} });
  }

  async loadLanguagePack(lang) {
    if (this.loadedLanguages.has(lang)) return true;
    try {
      const resp = await fetch(`/api/i18n/${lang}`);
      if (!resp.ok) throw new Error('Status ' + resp.status);
      const dict = await resp.json();
      this.registry[lang] = { default: dict };
      this.loadedLanguages.add(lang);
      this.notify();
      return true;
    } catch (e) {
      console.error(`[I18N] Failed to load language pack for '${lang}':`, e);
      return false;
    }
  }

  async setLanguage(lang) {
    this.currentLanguage = lang;
    window.__currentLanguage = lang;
    if (lang !== 'en') {
      await this.loadLanguagePack(lang);
    }
    this.notify();
    // Dispatch custom event so non-react elements (like charts) can listen to it
    window.dispatchEvent(new CustomEvent('vyom-language-changed', { detail: lang }));
  }

  t(key, params = {}, namespace = 'default') {
    if (!key || typeof key !== 'string') return key;
    const trimmed = key.trim();
    
    let ns = namespace;
    let lookupKey = trimmed;
    if (trimmed.includes('.')) {
      const parts = trimmed.split('.');
      ns = parts[0];
      lookupKey = parts.slice(1).join('.');
    }
    
    // Dynamic greeting handling
    if (lookupKey.startsWith("Good Morning,")) {
      const namePart = lookupKey.substring(13).replace(/!\\s*👋|!\\s*\\uD83D\\uDC4B/, "").trim();
      if (this.currentLanguage === 'hi') return `शुभ प्रभात, ${namePart}! 👋`;
      if (this.currentLanguage === 'pa') return `ਸ਼ੁਭ ਸਵੇਰ, ${namePart}! 👋`;
      if (this.currentLanguage === 'mr') return `शुभ प्रभात, ${namePart}! 👋`;
      if (this.currentLanguage === 'zh') return `早上好，${namePart}！👋`;
    } else if (lookupKey.startsWith("Good Afternoon,")) {
      const namePart = lookupKey.substring(15).replace(/!\\s*👋|!\\s*\\uD83D\\uDC4B/, "").trim();
      if (this.currentLanguage === 'hi') return `नमस्कार, ${namePart}! 👋`;
      if (this.currentLanguage === 'pa') return `ਨਮਸਕਾਰ, ${namePart}! 👋`;
      if (this.currentLanguage === 'mr') return `नमस्कार, ${namePart}! 👋`;
      if (this.currentLanguage === 'zh') return `下午好，${namePart}！👋`;
    } else if (lookupKey.startsWith("Good Evening,")) {
      const namePart = lookupKey.substring(13).replace(/!\\s*👋|!\\s*\\uD83D\\uDC4B/, "").trim();
      if (this.currentLanguage === 'hi') return `शुभ संध्या, ${namePart}! 👋`;
      if (this.currentLanguage === 'pa') return `ਸ਼ੁਭ ਸ਼ਾਮ, ${namePart}! 👋`;
      if (this.currentLanguage === 'mr') return `शुभ संध्या, ${namePart}! 👋`;
      if (this.currentLanguage === 'zh') return `晚上好，${namePart}！👋`;
    }

    let translation = this.lookup(this.currentLanguage, lookupKey, ns);
    if (translation === undefined) {
      translation = this.lookup(this.fallbackLanguage, lookupKey, ns);
    }
    
    if (translation === undefined) {
      return trimmed;
    }
    
    // Pluralization support
    if (typeof translation === 'object' && params.count !== undefined) {
      const form = params.count === 1 ? 'one' : 'other';
      translation = translation[form] || translation['other'] || lookupKey;
    }
    
    if (typeof translation !== 'string') return String(translation);
    
    // Parameter interpolation
    return translation.replace(/\\{(\\w+)\\}/g, (match, p) => {
      return params[p] !== undefined ? params[p] : match;
    });
  }

  lookup(lang, key, ns) {
    const pack = this.registry[lang];
    if (!pack) return undefined;
    if (pack[ns] && pack[ns][key] !== undefined) return pack[ns][key];
    if (pack[key] !== undefined) return pack[key];
    return undefined;
  }
}

window.i18n = new I18nManager();

function translateString(str, lang) {
  if (!str || typeof str !== 'string') return str;
  const val = window.i18n.t(str);
  
  const startWhitespace = str.match(/^\\s*/)[0];
  const endWhitespace = str.match(/\\s*$/)[0];
  return startWhitespace + val + endWhitespace;
}

const originalCreateElement = React.createElement;"""

    new_content = content[:start_idx] + replacement + content[end_idx + len(end_marker):]
    with open(vyom_html_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully replaced translations block using string slicing!")
