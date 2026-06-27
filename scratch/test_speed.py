import time, os, sys
sys.path.append(os.getcwd())
from scratch.test_email_pdf import mock_report

# Read the file
with open('email_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Google Fonts import
search_str = "@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');"
modified_content = content.replace(search_str, "/* Google Fonts Removed */")

# Temporarily execute the modified function
local_scope = {}
exec(modified_content, globals(), local_scope)

create_session_report_pdf = local_scope['create_session_report_pdf']

print('Generating PDF Run 1...')
t0 = time.time()
try:
    pdf_bytes = create_session_report_pdf(mock_report)
    print('Run 1 successful! Time taken:', time.time() - t0, 'seconds')
except Exception as e:
    import traceback
    traceback.print_exc()

print('Generating PDF Run 2...')
t1 = time.time()
try:
    pdf_bytes = create_session_report_pdf(mock_report)
    print('Run 2 successful! Time taken:', time.time() - t1, 'seconds')
except Exception as e:
    import traceback
    traceback.print_exc()
