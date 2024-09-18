import os
import importlib
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io


app = Flask(__name__)

# Configuration settings
app.config['UPLOAD_FOLDER'] = 'uploads/'
app.config['RESULT_FOLDER'] = 'results/'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 30  # Increase lock timeout
app.config['SECRET_KEY'] = 'your_secret_key_here'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Ensure the folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULT_FOLDER'], exist_ok=True)

# Dictionary to map reconciliation module names to their import paths
RECONCILIATION_MODULES = {
    'ocbc_bac': 'logic.ocbc_bac',
    'linkaja': 'logic.linkaja',
    'doku': 'logic.doku',
    'ewalletdana' : 'logic.ewalletdana'
}

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    files = db.relationship('UploadedFile', backref='uploader', lazy=True)
    results = db.relationship('ReconciliationResult', backref='owner', lazy=True)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150), nullable=False)
    filepath = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class ReconciliationResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150), nullable=False)
    filepath = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_request
def before_request():
    if not current_user.is_authenticated and request.endpoint not in ['login', 'register']:
        return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', modules=RECONCILIATION_MODULES)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful', 'success')
            return redirect(url_for('index'))
        else:
            flash('Login failed. Check your username and/or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        try:
            db.session.commit()
            flash('Account created!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_files():
    if request.method == 'POST':
        selected_module = request.form.get('reconciliation_module')

        if selected_module == 'doku':
            # Get files
            file1_files = request.files.getlist('file1')  # Multiple files for Source Data File 1
            file2 = request.files.get('file2')  # Single file for Source Data 2

            # Validate the number of file1 files
            if not file2 or len(file1_files) < 1 or len(file1_files) > 3:
                flash('Please upload 1 to 3 files for Source Data File 1 and one file for Source Data File 2.', 'danger')
                return redirect(url_for('index'))

            # Save File 1(s)
            file1_paths = []
            for f in file1_files:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if not os.path.isfile(file_path):  # Check if file already exists
                        f.save(file_path)
                    file1_paths.append(file_path)

            # Save File 2
            if file2 and file2.filename:
                file2_filename = secure_filename(file2.filename)
                file2_path = os.path.join(app.config['UPLOAD_FOLDER'], file2_filename)
                if not os.path.isfile(file2_path):  # Check if file already exists
                    file2.save(file2_path)
            else:
                flash('No file uploaded for Source Data File 2.', 'danger')
                return redirect(url_for('index'))

            try:
                # Save uploaded files info to database
                for path in file1_paths:
                    new_file = UploadedFile(filename=os.path.basename(path), filepath=path, user_id=current_user.id)
                    db.session.add(new_file)
                new_file2 = UploadedFile(filename=file2_filename, filepath=file2_path, user_id=current_user.id)
                db.session.add(new_file2)
                db.session.commit()

                # Load the selected reconciliation module dynamically
                module_name = RECONCILIATION_MODULES.get(selected_module)
                if not module_name:
                    raise ValueError('Invalid reconciliation module selected.')

                reconciliation_module = importlib.import_module(module_name)
                sheet_dict = reconciliation_module.reconcile_data(file1_paths, file2_path)

                # Save result to database
                result_filename = f'reconciliation_result_{selected_module}.xlsx'
                result_path = os.path.join(app.config['RESULT_FOLDER'], result_filename)

                with pd.ExcelWriter(result_path, engine='xlsxwriter') as writer:
                    for sheet_name, df in sheet_dict.items():
                        if not df.empty:
                            df.to_excel(writer, sheet_name=sheet_name, index=False)

                new_result = ReconciliationResult(filename=result_filename, filepath=result_path, user_id=current_user.id)
                db.session.add(new_result)
                db.session.commit()

                return redirect(url_for('show_result', filename=result_filename))

            except Exception as e:
                db.session.rollback()
                flash(f"An error occurred: {str(e)}", 'danger')
                return redirect(url_for('index'))
            
            #add new module here with elif

        else:
            file1 = request.files.get('file1')
            file2 = request.files.get('file2')

            if not (file1 and file2):
                flash('Please upload both files.', 'danger')
                return redirect(url_for('index'))

            file1_filename = secure_filename(file1.filename)
            file2_filename = secure_filename(file2.filename)
            file1_path = os.path.join(app.config['UPLOAD_FOLDER'], file1_filename)
            file2_path = os.path.join(app.config['UPLOAD_FOLDER'], file2_filename)
            if not os.path.isfile(file1_path):
                file1.save(file1_path)
            if not os.path.isfile(file2_path):
                file2.save(file2_path)

            try:
                new_file1 = UploadedFile(filename=file1_filename, filepath=file1_path, user_id=current_user.id)
                new_file2 = UploadedFile(filename=file2_filename, filepath=file2_path, user_id=current_user.id)
                db.session.add(new_file1)
                db.session.add(new_file2)
                db.session.commit()

                # Load the selected reconciliation module dynamically
                module_name = RECONCILIATION_MODULES.get(selected_module)
                if not module_name:
                    raise ValueError('Invalid reconciliation module selected.')

                reconciliation_module = importlib.import_module(module_name)
                sheet_dict = reconciliation_module.reconcile_data(file1_path, file2_path)

                # Save result to database
                result_filename = f'reconciliation_result_{selected_module}.xlsx'
                result_path = os.path.join(app.config['RESULT_FOLDER'], result_filename)

                with pd.ExcelWriter(result_path, engine='xlsxwriter') as writer:
                    for sheet_name, df in sheet_dict.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

                new_result = ReconciliationResult(filename=result_filename, filepath=result_path, user_id=current_user.id)
                db.session.add(new_result)
                db.session.commit()

                return redirect(url_for('show_result', filename=result_filename))

            except Exception as e:
                db.session.rollback()
                flash(f"An error occurred: {str(e)}", 'danger')
                return redirect(url_for('index'))

    flash('Please upload the required files and select a reconciliation module.', 'danger')
    return redirect(url_for('index'))


@app.route('/result')
@login_required
def show_result():
    filename = request.args.get('filename')
    if filename:
        return render_template('result.html', filename=filename)
    return "No result available.", 404

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    result_path = os.path.join(app.config['RESULT_FOLDER'], filename)
    if os.path.exists(result_path):
        return send_file(result_path, as_attachment=True)
    return "File not found.", 404

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()  # Create database tables
            print("Database tables created successfully.")
        except Exception as e:
            print(f"Error creating database tables: {str(e)}")
    app.run(debug=True)
