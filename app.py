import os
import json
import logging
import re
import datetime
from uuid import uuid4
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from pymongo import MongoClient
from bson.objectid import ObjectId
from PyPDF2 import PdfReader
from docx import Document
from groq import Groq
from dotenv import load_dotenv
from prompt import generate_resume_prompt, generate_job_prompt
from collections import defaultdict

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
app.config.from_object('config.Config')

# Configure MongoDB
client = MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017/'))
db = client['resume_parser']
users_collection = db['users']
resumes_collection = db['parsed_resumes']
recruiters_collection = db['recruiters']
jobs_collection = db['jobs']
applications_collection = db['application_collections']


# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PARSED_RESUMES_FOLDER'], exist_ok=True)
os.makedirs(app.config['PARSED_JOB_PATH'], exist_ok=True)

# Models
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']

class Recruiter(UserMixin):
    def __init__(self, recruiter_data):
        self.id = str(recruiter_data['_id'])
        self.email = recruiter_data['email']
        self.password_hash = recruiter_data['password_hash']
        self.company = recruiter_data.get('company', '')
        self.name = recruiter_data.get('name', '')

# Common Method for Recruiter and User
@login_manager.user_loader
def load_user(user_id):
    # Check both collections
    user_data = users_collection.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    
    recruiter_data = recruiters_collection.find_one({'_id': ObjectId(user_id)})
    if recruiter_data:
        return Recruiter(recruiter_data)
    
    return None

# ----------------------------------------------------------------------------------
# Recruiter routes and services
# ----------------------------------------------------------------------------------


@app.route('/login_recruiter', methods=['GET', 'POST'])
def login_recruiter():
    if current_user.is_authenticated:
        return redirect(url_for('recruiter_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        recruiter_data = recruiters_collection.find_one({'email': email})
        if recruiter_data and check_password_hash(recruiter_data['password_hash'], password):
            recruiter = Recruiter(recruiter_data)
            login_user(recruiter)
            return redirect(url_for('recruiter_dashboard'))
        
        flash('Invalid email or password', 'error')
        return redirect(url_for('login_recruiter'))
    
    return render_template('recruiter_login.html')

@app.route('/signup_recruiter', methods=['GET', 'POST'])
def signup_recruiter():
    if current_user.is_authenticated:
        return redirect(url_for('recruiter_dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name')
        company = request.form.get('company')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('signup_recruiter'))
            
        if recruiters_collection.find_one({'email': email}):
            flash('Email already exists', 'error')
            return redirect(url_for('signup_recruiter'))
        
        recruiter_data = {
            'email': email,
            'password_hash': generate_password_hash(password),
            'name': name,
            'company': company,
            'created_at': datetime.datetime.utcnow(),
            'updated_at': datetime.datetime.utcnow()
        }
        recruiters_collection.insert_one(recruiter_data)
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login_recruiter'))
    
    return render_template('recruiter_signup.html')

@app.route('/recruiter/dashboard')
@login_required
def recruiter_dashboard():
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    jobs = list(jobs_collection.find({'recruiter_id': ObjectId(current_user.id)}))
    return render_template('recruiter_dashboard.html', jobs=jobs)

@app.route('/recruiter/create_job', methods=['GET', 'POST'])
@login_required
def create_job():
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file uploaded', 'error')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
        print(file.filename)
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(temp_path)
                
                file_type = filename.split('.')[-1].lower()
                job_text = extract_text_from_file(temp_path, file_type)
                
                # Call LLM to parse job description
                llm_response = call_job_llm(job_text)
                
                if not llm_response.get('output'):
                    flash('Failed to parse job description', 'error')
                    return redirect(request.url)
                
                parsed_job = json.loads(llm_response['output'])
                
                # Save to MongoDB
                job_data = {
                    'recruiter_id': ObjectId(current_user.id),
                    'company': current_user.company,
                    'original_filename': filename,
                    'job_description': job_text,
                    'parsed_data': parsed_job,
                    'created_at': datetime.datetime.utcnow(),
                    'updated_at': datetime.datetime.utcnow()
                }
                jobs_collection.insert_one(job_data)
                
                os.remove(temp_path)
                
                # Save to file system (optional)
                parsed_filename = f"parsed_{filename.split('.')[0]}.json"
                parsed_job_path = os.path.join(app.config['PARSED_JOB_PATH'], parsed_filename)
                
                with open(parsed_job_path, 'w') as f:
                    json.dump(parsed_job, f, indent=4)
                flash('Job created successfully!', 'success')

                return redirect(url_for('view_job', job_id=str(job_data['_id'])))     
                
            except Exception as e:
                logger.error(f"Error processing job file: {str(e)}")
                flash('Error processing job description', 'error')
                return redirect(request.url)
        else:
            flash('File type not allowed', 'error')
            return redirect(request.url)
    
    return render_template('create_job.html')

@app.route('/recruiter/job/<job_id>')
@login_required
def view_job(job_id):
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    job = jobs_collection.find_one({
        '_id': ObjectId(job_id),
        'recruiter_id': ObjectId(current_user.id)
    })
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('recruiter_dashboard'))
    
    return render_template('view_job.html', job=job)

def call_job_llm(job_text: str) -> dict:
    """Calls the Groq API to parse job description text."""
    try:
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        prompt = generate_job_prompt(job_text)  # Assuming this function exists in prompt.py
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful job description parser."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if hasattr(response, "usage") else 0
        
        json_content = extract_json_from_response(content)
        return {"output": json_content, "tokens": tokens}
    except Exception as e:
        logger.error(f"Error in call_job_llm: {str(e)}")
        return {"output": "", "error": str(e), "tokens": 0}

def extract_json_from_response(content: str) -> str:
    """Extracts JSON content from the LLM response."""
    json_match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    
    try:
        start = content.find('{')
        end = content.rfind('}') + 1
        if start != -1 and end != -1:
            potential_json = content[start:end]
            json.loads(potential_json)
            return potential_json
    except json.JSONDecodeError:
        pass
    
    return content.strip()


# ----------------------------------------------------------------------------------
# Applicant Screening
# ----------------------------------------------------------------------------------

@app.route('/recruiter/applicants')
@login_required
def view_applicants():
    """View all applicants across all jobs posted by this recruiter"""
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Get all jobs posted by this recruiter
    recruiter_jobs = list(jobs_collection.find(
        {'recruiter_id': ObjectId(current_user.id)},
        {'_id': 1, 'parsed_data.title': 1}
    ))
    
    job_ids = [job['_id'] for job in recruiter_jobs]
    
    # Get all applications for these jobs with user and resume info
    applications = list(applications_collection.aggregate([
        {
            '$match': {
                'job_id': {'$in': job_ids}
            }
        },
        {
            '$lookup': {
                'from': 'users',
                'localField': 'user_id',
                'foreignField': '_id',
                'as': 'user'
            }
        },
        {
            '$unwind': '$user'
        },
        {
            '$lookup': {
                'from': 'parsed_resumes',
                'localField': 'resume_id',
                'foreignField': '_id',
                'as': 'resume'
            }
        },
        {
            '$unwind': '$resume'
        },
        {
            '$lookup': {
                'from': 'jobs',
                'localField': 'job_id',
                'foreignField': '_id',
                'as': 'job'
            }
        },
        {
            '$unwind': '$job'
        },
        {
            '$project': {
                'user_id': 1,
                'user_email': '$user.email',
                'job_title': '$job.parsed_data.title',
                'resume_data': '$resume',
                'status': 1,
                'applied_at': 1,
                'cover_message': 1
            }
        }
    ]))
    
    return render_template('recruiter/applicants.html', 
                         applications=applications,
                         total_applicants=len(applications))

@app.route('/recruiter/job/<job_id>/applicants')
@login_required
def view_job_applicants(job_id):
    """View applicants for a specific job with statistics"""
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    # Verify the job belongs to this recruiter
    job = jobs_collection.find_one({
        '_id': ObjectId(job_id),
        'recruiter_id': ObjectId(current_user.id)
    })
    
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('recruiter_dashboard'))
    
    # Get all applications for this job
    applications = list(applications_collection.aggregate([
        {
            '$match': {
                'job_id': ObjectId(job_id)
            }
        },
        {
            '$lookup': {
                'from': 'users',
                'localField': 'user_id',
                'foreignField': '_id',
                'as': 'user'
            }
        },
        {
            '$unwind': '$user'
        },
        {
            '$lookup': {
                'from': 'parsed_resumes',
                'localField': 'resume_id',
                'foreignField': '_id',
                'as': 'resume'
            }
        },
        {
            '$unwind': '$resume'
        },
        {
            '$project': {
                '_id': 1,
                'resume_id': 1,
                'user_id': 1,
                'user_email': '$user.email',
                'resume_data': '$resume.parsed_data',  # Access parsed_data directly
                'status': 1,
                'applied_at': 1,
                'cover_message': 1
            }
        }
    ]))
    
    # Calculate statistics
    status_counts = defaultdict(int)
    skills = defaultdict(int)
    experience_levels = defaultdict(int)
    total_applicants = len(applications)
    
    for app in applications:
        # Status counts
        status_counts[app['status']] += 1
        
        # Skills analysis
        resume_data = app.get('resume_data', {})
        for skill in resume_data.get('skills', []):
            skills[skill['skill_name']] += 1
        
        # Experience level calculation based on dates
        total_exp = 0
        for exp in resume_data.get('experience', []):
            if exp.get('start_date') and exp.get('end_date'):
                try:
                    start = datetime.strptime(exp['start_date'], "%Y-%m-%d")
                    end = datetime.strptime(exp['end_date'], "%Y-%m-%d") if exp['end_date'] else datetime.now()
                    total_exp += (end - start).days / 365.25
                except:
                    continue
        
        exp_level = 'Junior' if total_exp < 3 else 'Mid-level' if total_exp < 7 else 'Senior'
        experience_levels[exp_level] += 1
    
    # Sort skills by frequency
    top_skills = sorted(skills.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return render_template('recruiter/job_applicants.html',
                         job=job,
                         applications=applications,
                         total_applicants=total_applicants,
                         status_counts=status_counts,
                         top_skills=top_skills,
                         experience_levels=experience_levels)

# Add this new route for viewing individual resumes
@app.route('/recruiter/view_resume/<resume_id>')
@login_required
def recruiter_view_resume(resume_id):
    if not isinstance(current_user, Recruiter):
        flash('Access denied', 'error')
        return redirect(url_for('index'))
    
    resume = resumes_collection.find_one({'_id': ObjectId(resume_id)})
    
    if not resume:
        flash('Resume not found', 'error')
        return redirect(url_for('recruiter_dashboard'))
    
    # Verify the recruiter has access to this resume (through an application)
    application = applications_collection.find_one({
        'resume_id': ObjectId(resume_id),
        'job_id': {'$in': jobs_collection.find(
            {'recruiter_id': ObjectId(current_user.id)},
            {'_id': 1}
        ).distinct('_id')
    }})
    
    if not application:
        flash('Access to this resume is restricted', 'error')
        return redirect(url_for('recruiter_dashboard'))
    
    return render_template('recruiter/resume_view.html', resume=resume)





# User/Applicant Specific Routes, Services 
def call_llm(resume_text: str) -> dict:
    """Calls the Groq API to parse resume text."""
    try:
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        prompt = generate_resume_prompt(resume_text)
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful resume parser."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if hasattr(response, "usage") else 0
        
        json_content = extract_json_from_response(content)
        return {"output": json_content, "tokens": tokens}
    except Exception as e:
        logger.error(f"Error in call_llm: {str(e)}")
        return {"output": "", "error": str(e), "tokens": 0}

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """Extracts text from different file types with encoding fallback."""
    try:
        if file_type == 'pdf':
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                text = '\n'.join([page.extract_text() for page in reader.pages])
        elif file_type == 'docx':
            doc = Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
        else:  # txt or other text files
            # Try UTF-8 first, then fall back to other common encodings
            encodings = ['utf-8', 'latin-1', 'windows-1252', 'iso-8859-1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # If all encodings fail, try with error handling
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
        return text
    except Exception as e:
        logger.error(f"Error extracting text: {str(e)}")
        raise


@app.route('/')
@login_required  # Add this decorator to protect the index page
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:  # If already logged in, redirect to dashboard
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if users_collection.find_one({'email': email}):
            flash('Email already exists', 'error')
            return redirect(url_for('signup'))
        
        user_data = {
            'email': email,
            'password_hash': generate_password_hash(password),
            'created_at': datetime.datetime.utcnow()
        }
        users_collection.insert_one(user_data)
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:  # If already logged in, redirect to dashboard
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_data = users_collection.find_one({'email': email})
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
            login_user(user)
            # next_page = request.args.get('next')  
            return redirect(url_for('dashboard'))  # Redirect to next page or dashboard
        
        flash('Invalid email or password', 'error')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))  # Redirect to login after logout

@app.route('/dashboard')
@login_required
def dashboard():
    user_resumes = list(resumes_collection.find({'user_id': ObjectId(current_user.id)}))
    
    # Get recent applications
    applications = list(applications_collection.aggregate([
        {
            '$match': {
                'user_id': ObjectId(current_user.id)
            }
        },
        {
            '$lookup': {
                'from': 'jobs',
                'localField': 'job_id',
                'foreignField': '_id',
                'as': 'job'
            }
        },
        {
            '$unwind': '$job'
        },
        {
            '$sort': {
                'applied_at': -1
            }
        },
        {
            '$limit': 3
        }
    ]))
    
    return render_template('dashboard.html', 
                         resumes=user_resumes,
                         applications=applications)
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(temp_path)
            
            file_type = filename.split('.')[-1].lower()
            resume_text = extract_text_from_file(temp_path, file_type)
            
            llm_response = call_llm(resume_text)
            
            if not llm_response.get('output'):
                return jsonify({"error": llm_response.get('error', 'Failed to parse resume')}), 500
            
            parsed_resume = json.loads(llm_response['output'])
            
            # Save to MongoDB
            resume_data = {
                'user_id': ObjectId(current_user.id),
                'original_filename': filename,
                'parsed_data': parsed_resume,
                'created_at': datetime.datetime.utcnow()
            }
            resumes_collection.insert_one(resume_data)
            
            # Save to file system (optional)
            parsed_filename = f"parsed_{filename.split('.')[0]}.json"
            parsed_path = os.path.join(app.config['PARSED_RESUMES_FOLDER'], parsed_filename)
            
            with open(parsed_path, 'w') as f:
                json.dump(parsed_resume, f, indent=4)
            
            os.remove(temp_path)
            
            return jsonify({
                "status": "success",
                "parsed_resume": parsed_resume,
                "tokens_used": llm_response['tokens'],
                "filename": filename
            })
            
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "File type not allowed"}), 400

@app.route('/resume/<resume_id>')
@login_required
def view_resume(resume_id):
    resume = resumes_collection.find_one({
        '_id': ObjectId(resume_id),
        'user_id': ObjectId(current_user.id)
    })
    
    if not resume:
        flash('Resume not found', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('resume_view.html', resume=resume)

@app.route('/jobs')
@login_required
def browse_jobs():
    # Get all active jobs with pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    jobs = list(jobs_collection.find({}).skip((page-1)*per_page).limit(per_page))
    total_jobs = jobs_collection.count_documents({})
    
    return render_template('jobs/browse.html', 
                         jobs=jobs,
                         current_page=page,
                         total_pages=(total_jobs // per_page) + 1)

@app.route('/jobs/<job_id>')
@login_required
def job_detail(job_id):
    job = jobs_collection.find_one({'_id': ObjectId(job_id)})
    if not job:
        flash('Job not found', 'error')
        return redirect(url_for('browse_jobs'))
    
    # Check if user has already applied
    has_applied = applications_collection.find_one({
        'user_id': ObjectId(current_user.id),
        'job_id': ObjectId(job_id)
    })
    
    # Get user's resumes for application dropdown
    user_resumes = list(resumes_collection.find({'user_id': ObjectId(current_user.id)}))
    
    return render_template('jobs/detail.html', 
                         job=job,
                         has_applied=bool(has_applied),
                         resumes=user_resumes)

@app.route('/jobs/<job_id>/apply', methods=['POST'])
@login_required
def apply_for_job(job_id):
    print("request")
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    resume_id = data.get('resume_id')
    cover_message = data.get('cover_message', '')
    print(resume_id)
    print(cover_message)
    
    # Validate
    job = jobs_collection.find_one({'_id': ObjectId(job_id)})
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    resume = resumes_collection.find_one({
        '_id': ObjectId(resume_id),
        'user_id': ObjectId(current_user.id)
    })
    if not resume:
        return jsonify({"error": "Resume not found"}), 404
    
    # Check if already applied
    existing_application = applications_collection.find_one({
        'user_id': ObjectId(current_user.id),
        'job_id': ObjectId(job_id)
    })
    if existing_application:
        return jsonify({"error": "You've already applied for this job"}), 400
    
    # Create application
    application_data = {
        'user_id': ObjectId(current_user.id),
        'job_id': ObjectId(job_id),
        'resume_id': ObjectId(resume_id),
        'cover_message': cover_message,
        'status': 'submitted',
        'applied_at': datetime.datetime.utcnow(),
        'updated_at': datetime.datetime.utcnow()
    }
    applications_collection.insert_one(application_data)
    
    return jsonify({
        "status": "success",
        "message": "Application submitted successfully"
    }), 200

@app.route('/applications')
@login_required
def my_applications():
    # Get user's applications with job details
    applications = list(applications_collection.aggregate([
        {
            '$match': {
                'user_id': ObjectId(current_user.id)
            }
        },
        {
            '$lookup': {
                'from': 'jobs',
                'localField': 'job_id',
                'foreignField': '_id',
                'as': 'job_info'
            }
        },
        {
            '$unwind': '$job_info'
        },
        {
            '$lookup': {
                'from': 'parsed_resumes',
                'localField': 'resume_id',
                'foreignField': '_id',
                'as': 'resume_info'
            }
        },
        {
            '$unwind': '$resume_info'
        },
        {
            '$sort': {
                'applied_at': -1
            }
        },
        {
            '$project': {
                'status': 1,
                'applied_at': 1,
                'cover_message': 1,
                'job_title': '$job_info.parsed_data.title',
                'company': '$job_info.company',
                'resume_name': '$resume_info.original_filename',
                'job_id': '$job_info._id'
            }
        }
    ]))
    
    return render_template('applications/list.html', applications=applications)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

if __name__ == '__main__':
    app.run(debug=True)