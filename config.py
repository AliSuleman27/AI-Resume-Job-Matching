import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    UPLOAD_FOLDER = 'uploads'
    PARSED_RESUMES_FOLDER = 'parsed_resumes'
    PARSED_JOB_PATH = 'parsed_jobs'
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')