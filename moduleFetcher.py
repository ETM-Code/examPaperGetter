import os
import requests
from urllib.parse import urlparse, unquote
import subprocess
from pathlib import Path
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('ACCESS_TOKEN')
base_url = os.getenv('BASE_URL')

class CanvasDownloader:
    def __init__(self, access_token, base_url):
        self.access_token = access_token
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {access_token}'
        }
        self.download_config = self._load_download_config()
        
    def _load_download_config(self):
        """Load download configuration from downSubjects.txt"""
        config = {}
        try:
            with open('downSubjects.txt', 'r') as f:
                for line in f:
                    if line.strip():
                        parts = line.strip().split(':')
                        if len(parts) >= 3:  # Now expecting nickname:type:path
                            nickname = parts[0].strip()
                            download_type = parts[1].strip().lower()
                            save_path = parts[2].strip().strip("'")  # Remove quotes if present
                            config[nickname] = {
                                'type': download_type,
                                'path': os.path.expanduser(save_path)  # Handle ~ in paths
                            }
        except FileNotFoundError:
            print("Warning: downSubjects.txt not found. Will download all subjects.")
        return config

    def get_courses(self):
        """Get list of active courses"""
        url = f'{self.base_url}/api/v1/courses'
        params = {
            'enrollment_state': 'active',
            'per_page': 100
        }
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()

    def get_modules(self, course_id):
        """Get all modules for a course"""
        url = f'{self.base_url}/api/v1/courses/{course_id}/modules'
        params = {'per_page': 100}
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()

    def get_module_items(self, course_id, module_id):
        """Get all items in a module"""
        url = f'{self.base_url}/api/v1/courses/{course_id}/modules/{module_id}/items'
        params = {'per_page': 100}
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()

    def get_files(self, course_id):
        """Get all files in a course"""
        url = f'{self.base_url}/api/v1/courses/{course_id}/files'
        params = {'per_page': 100}
        response = requests.get(url, headers=self.headers, params=params)
        return response.json()

    def convert_to_pdf(self, input_path, pdf_dir):
        """Convert Office documents to PDF using LibreOffice"""
        if not os.path.exists(input_path):
            return None
            
        # Get the filename
        filename = os.path.basename(input_path)
        
        # Construct the output PDF path in the subject's PDF directory
        output_pdf = os.path.join(pdf_dir, os.path.splitext(filename)[0] + '.pdf')
        
        # If PDF already exists and is newer than the source file, skip conversion
        if os.path.exists(output_pdf):
            if os.path.getmtime(output_pdf) > os.path.getmtime(input_path):
                print(f"PDF version already exists and is up to date: {output_pdf}")
                return output_pdf
        
        try:
            # Convert to PDF using LibreOffice
            subprocess.run([
                'soffice',
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', pdf_dir,
                input_path
            ], check=True, capture_output=True)
            
            if os.path.exists(output_pdf):
                print(f"Successfully converted to PDF: {output_pdf}")
                return output_pdf
        except subprocess.CalledProcessError as e:
            print(f"Failed to convert {input_path} to PDF: {e}")
        except Exception as e:
            print(f"Error during PDF conversion: {e}")
        
        return None

    def should_download_course(self, course_name):
        """Check if course should be downloaded based on downSubjects.txt"""
        if not self.download_config:  # If no config file, download everything
            return True, 'both', 'canvas_downloads'
            
        for nickname, config in self.download_config.items():
            if nickname.lower() in course_name.lower():
                return True, config['type'], config['path']
        return False, None, None

    def file_needs_download(self, filepath, file_data):
        """Check if file needs to be downloaded based on existence and modification time"""
        if not os.path.exists(filepath):
            return True
            
        # Get the remote file's modification time
        remote_modified = file_data.get('modified_at')
        if not remote_modified:
            return True
            
        # Get local file's modification time
        local_modified = os.path.getmtime(filepath)
        

        
        remote_dt = datetime.fromisoformat(remote_modified.replace('Z', '+00:00'))
        local_dt = datetime.fromtimestamp(local_modified, pytz.UTC)
        
        # Download if remote file is newer
        return remote_dt > local_dt

    def download_file(self, url, filepath, pdf_dir):
        """Download a file from Canvas"""
        # If the url is a JSON response, extract the actual download URL
        file_data = url if isinstance(url, dict) else {'url': url}
        download_url = file_data.get('url')
        
        if not download_url:
            print(f"Warning: Could not get download URL for {filepath}")
            return False
            
        # Check if file needs to be downloaded
        if not self.file_needs_download(filepath, file_data):
            print(f"File already exists and is up to date: {filepath}")
            return True
            
        # Add download parameters if they're not already present
        if 'download_frd=1' not in download_url:
            download_url += '&download_frd=1' if '?' in download_url else '?download_frd=1'
            
        response = requests.get(download_url, headers=self.headers, stream=True)
        if response.status_code == 200:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Successfully downloaded: {filepath}")
            
            # Convert to PDF if it's an Office document
            if filepath.lower().endswith(('.docx', '.pptx', '.doc', '.ppt')):
                self.convert_to_pdf(filepath, pdf_dir)
            
            return True
        else:
            print(f"Failed to download {filepath}: Status code {response.status_code}")
        return False

    def download_course_files(self, course, base_path):
        """Download all files from the Files section of a course"""
        course_id = course['id']
        course_name = course['name']
        
        # Create course directory
        course_dir = base_path
        os.makedirs(course_dir, exist_ok=True)
        
        # Create PDF directory for this subject
        pdf_dir = os.path.join(course_dir, 'PDF_Versions')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Get all files
        try:
            files = self.get_files(course_id)
            if isinstance(files, str):
                print(f"Warning: Unexpected response for course files: {files}")
                return
            
            if not isinstance(files, list):
                print(f"Warning: Unexpected response type for course files: {type(files)}")
                return
            
            for file in files:
                if not isinstance(file, dict):
                    print(f"Warning: Unexpected file data type: {type(file)}")
                    continue
                    
                filename = file.get('filename', '')
                if filename:
                    filename = filename.replace('+', ' ')
                    filepath = os.path.join(course_dir, filename)
                    print(f"Processing file: {filepath}")
                    self.download_file(file, filepath, pdf_dir)
        except Exception as e:
            print(f"Error downloading files for course {course_name}: {str(e)}")

    def download_course_modules(self, course, base_path):
        """Download all module content for a course"""
        course_id = course['id']
        course_name = course['name']
        
        # Create course directory and PDF directory
        course_dir = base_path
        os.makedirs(course_dir, exist_ok=True)
        pdf_dir = os.path.join(course_dir, 'PDF_Versions')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Get all modules
        try:
            modules = self.get_modules(course_id)
            if isinstance(modules, str):
                print(f"Warning: Unexpected response for course modules: {modules}")
                return
                
            if not isinstance(modules, list):
                print(f"Warning: Unexpected response type for course modules: {type(modules)}")
                return
            
            for module in modules:
                if not isinstance(module, dict):
                    print(f"Warning: Unexpected module data type: {type(module)}")
                    continue
                    
                module_name = module.get('name', 'Unnamed Module')
                
                # Get module items
                try:
                    items = self.get_module_items(course_id, module['id'])
                    if not isinstance(items, list):
                        print(f"Warning: Unexpected items response type: {type(items)}")
                        continue
                    
                    # If module has only one item, don't create a module directory
                    if len(items) == 1:
                        target_dir = course_dir
                    else:
                        target_dir = os.path.join(course_dir, module_name)
                        os.makedirs(target_dir, exist_ok=True)
                    
                    for item in items:
                        if not isinstance(item, dict):
                            print(f"Warning: Unexpected item data type: {type(item)}")
                            continue
                            
                        if item.get('type') in ['File', 'Page', 'Attachment']:
                            url = item.get('url')
                            if url:
                                try:
                                    # Make a request to get the file details
                                    response = requests.get(url, headers=self.headers)
                                    if response.status_code == 200:
                                        file_data = response.json()
                                        if isinstance(file_data, dict):
                                            filename = file_data.get('filename', '')
                                            if not filename:
                                                filename = f"{item.get('title', 'untitled')}.html"
                                            
                                            filename = filename.replace('+', ' ')
                                            filepath = os.path.join(target_dir, filename)
                                            print(f"Processing: {filepath}")
                                            self.download_file(file_data, filepath, pdf_dir)
                                        else:
                                            print(f"Warning: Unexpected file data response: {type(file_data)}")
                                except Exception as e:
                                    print(f"Error processing module item: {str(e)}")
                except Exception as e:
                    print(f"Error getting module items: {str(e)}")
        except Exception as e:
            print(f"Error downloading modules for course {course_name}: {str(e)}")

    def download_course_content(self, course):
        """Download content for a course based on configuration"""
        should_download, download_type, base_path = self.should_download_course(course['name'])
        
        if not should_download:
            print(f"Skipping course: {course['name']} (not in downSubjects.txt)")
            return
            
        print(f"\nProcessing course: {course['name']}")
        
        if download_type in ['modules', 'both']:
            print("Downloading modules...")
            self.download_course_modules(course, base_path)
            
        if download_type in ['files', 'both']:
            print("Downloading files...")
            self.download_course_files(course, base_path)

def main():
    # Replace these with your Canvas instance details
    ACCESS_TOKEN = api_key
    BASE_URL = base_url
    
    downloader = CanvasDownloader(ACCESS_TOKEN, BASE_URL)
    
    # Get and process each course
    courses = downloader.get_courses()
    for course in courses:
        downloader.download_course_content(course)

if __name__ == '__main__':
    main()