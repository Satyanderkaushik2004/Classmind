vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update setLanguage inside appCtxValue
old_app_ctx_set_lang = """    language: appLang,
    setLanguage: (newLang) => {
      localStorage.setItem('cm_lang', newLang);
      window.__currentLanguage = newLang;
      setAppLang(newLang);
    },"""

new_app_ctx_set_lang = """    language: appLang,
    setLanguage: (newLang) => {
      localStorage.setItem('cm_lang', newLang);
      window.__currentLanguage = newLang;
      window.i18n.setLanguage(newLang).then(() => {
        setAppLang(newLang);
      });
    },"""

# 2. Update StudentTaskView destructuring of useContext(AppCtx)
old_student_destruct = """  const {
    add,
    theme,
    setTheme
  } = useContext(AppCtx);"""

new_student_destruct = """  const {
    add,
    theme,
    setTheme,
    language,
    setLanguage
  } = useContext(AppCtx);"""

# 3. Update LanguageSelectorModal inside StudentTaskView
old_student_lang_modal = """                React.createElement(LanguageSelectorModal, {
                  open: profileLangModalOpen,
                  onClose: () => setProfileLangModalOpen(false),
                  currentLanguage: (() => { try { return localStorage.getItem('cm_lang')||'en'; } catch{return 'en';} })(),
                  onSelectLanguage: (lang) => { try { localStorage.setItem('cm_lang', lang); window.__currentLanguage = lang; } catch{} setProfileLangModalOpen(false); add('Language updated!','success'); }
                })"""

new_student_lang_modal = """                React.createElement(LanguageSelectorModal, {
                  open: profileLangModalOpen,
                  onClose: () => setProfileLangModalOpen(false),
                  currentLanguage: language || 'en',
                  onSelectLanguage: (lang) => {
                    setLanguage(lang);
                    setProfileLangModalOpen(false);
                    add('Language updated!', 'success');
                  }
                })"""

def replace_exact(old_code, new_code):
    global content
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("Replaced block successfully.")
    else:
        # Normalize CRLF and spaces
        norm_old = old_code.replace("\r\n", "\n").strip()
        norm_content = content.replace("\r\n", "\n")
        if norm_old in norm_content:
            content = norm_content.replace(norm_old, new_code.replace("\r\n", "\n"))
            print("Replaced block successfully after CRLF normalization.")
        else:
            print("Could not find block to replace.")

replace_exact(old_app_ctx_set_lang, new_app_ctx_set_lang)
replace_exact(old_student_destruct, new_student_destruct)
replace_exact(old_student_lang_modal, new_student_lang_modal)

with open(vyom_html_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Language change fixes completed.")
