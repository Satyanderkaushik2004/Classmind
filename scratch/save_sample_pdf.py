import sys
import os

# Ensure project root is in python path
sys.path.append(os.getcwd())

from email_service import create_session_report_pdf
from scratch.test_email_pdf import mock_report

def main():
    print("Generating sample report PDF...")
    try:
        pdf_bytes = create_session_report_pdf(mock_report)
        output_path = "sample_report.pdf"
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"SUCCESS: Sample report PDF saved to: {os.path.abspath(output_path)}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
