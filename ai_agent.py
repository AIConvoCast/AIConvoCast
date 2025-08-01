#!/usr/bin/env python3
"""
AI Agent for Podcast Workflow Automation
Handles manual tasks like copying podcast data and uploading files to Google Drive.
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Google APIs
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.cloud import storage

# Environment
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PodcastAgent:
    """AI Agent for automating podcast workflow tasks."""
    
    def __init__(self):
        """Initialize the agent with API credentials and settings."""
        self.setup_google_credentials()
        self.setup_gcs_client()
        self.load_settings()
        
    def setup_google_credentials(self):
        """Setup Google API credentials."""
        try:
            # Use the same service account as the main pipeline
            creds_file = 'jmio-google-api.json'
            if not os.path.exists(creds_file):
                raise FileNotFoundError(f"Google credentials file not found: {creds_file}")
            
            # Scopes for Sheets and Drive access
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/drive.file'
            ]
            
            self.creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
            self.sheets_client = gspread.authorize(self.creds)
            self.drive_service = build('drive', 'v3', credentials=self.creds)
            
            logger.info("✅ Google API credentials loaded successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup Google credentials: {e}")
            raise
    
    def setup_gcs_client(self):
        """Setup Google Cloud Storage client."""
        try:
            self.gcs_client = storage.Client.from_service_account_json('jmio-google-api.json')
            self.bucket_name = 'jmio-podcast-storage'
            self.bucket = self.gcs_client.bucket(self.bucket_name)
            logger.info("✅ Google Cloud Storage client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to setup GCS client: {e}")
            raise
    
    def load_settings(self):
        """Load agent settings."""
        self.settings = {
            'spreadsheet_email': os.getenv('SHARE_SHEET_WITH_EMAIL'),
            'drive_folder_id': '13G1L2HSLwdPJHuUoKT0DT8j1IiqHpm8u',  # From the provided URL
            'gcs_podcasts_folder': 'podcasts/',
            'supported_audio_formats': ['.mp3', '.wav', '.m4a']
        }
        
        if not self.settings['spreadsheet_email']:
            raise ValueError("SHARE_SHEET_WITH_EMAIL not found in environment variables")
        
        logger.info(f"✅ Agent settings loaded for: {self.settings['spreadsheet_email']}")
    
    def get_latest_podcast_output(self) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Get the latest podcast output from Google Sheets.
        Returns: (title, description, output_id)
        """
        try:
            # Open the spreadsheet
            spreadsheet = self.sheets_client.open_by_key(self.settings['spreadsheet_email'])
            outputs_sheet = spreadsheet.worksheet('Outputs')
            
            # Get all data
            data = outputs_sheet.get_all_records()
            
            if not data:
                logger.warning("No data found in Outputs sheet")
                return None, None, None
            
            # Find the latest row (highest Output ID)
            latest_row = max(data, key=lambda x: int(x.get('Output ID', 0)))
            output_id = latest_row.get('Output ID')
            
            # Look for title and description in the output columns
            title, description = self.extract_title_and_description(latest_row)
            
            if title:
                logger.info(f"📝 Found latest podcast: ID {output_id} - {title[:50]}...")
                return title, description, output_id
            else:
                logger.warning(f"No title found in latest output ID {output_id}")
                return None, None, output_id
                
        except Exception as e:
            logger.error(f"❌ Failed to get latest podcast output: {e}")
            return None, None, None
    
    def extract_title_and_description(self, row_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract title and description from output row data.
        Looks through all output columns for title/description patterns.
        """
        title = None
        description = None
        
        # Look through all columns for title and description
        for key, value in row_data.items():
            if not value or not isinstance(value, str):
                continue
                
            # Look for title patterns
            title_match = re.search(r'Title:\s*([^\n]+)', value, re.IGNORECASE)
            if title_match and not title:
                title = title_match.group(1).strip()
            
            # Look for description patterns
            desc_match = re.search(r'Description(?:\s+Short)?:\s*([^\n]+)', value, re.IGNORECASE)
            if desc_match and not description:
                description = desc_match.group(1).strip()
        
        return title, description
    
    def get_latest_podcast_file_from_gcs(self) -> Optional[str]:
        """
        Get the latest podcast file from Google Cloud Storage podcasts folder.
        Returns: blob name of the latest file
        """
        try:
            # List all files in the podcasts folder
            blobs = list(self.bucket.list_blobs(prefix=self.settings['gcs_podcasts_folder']))
            
            # Filter for audio files
            audio_blobs = []
            for blob in blobs:
                if any(blob.name.lower().endswith(ext) for ext in self.settings['supported_audio_formats']):
                    audio_blobs.append(blob)
            
            if not audio_blobs:
                logger.warning("No audio files found in GCS podcasts folder")
                return None
            
            # Sort by creation time (most recent first)
            latest_blob = max(audio_blobs, key=lambda b: b.time_created)
            
            logger.info(f"🎵 Found latest podcast file: {latest_blob.name}")
            return latest_blob.name
            
        except Exception as e:
            logger.error(f"❌ Failed to get latest podcast file from GCS: {e}")
            return None
    
    def sanitize_filename(self, title: str) -> str:
        """
        Sanitize title for use as filename.
        """
        # Remove invalid characters for filenames
        sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
        # Replace multiple spaces with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)
        # Trim and limit length
        sanitized = sanitized.strip()[:100]
        return sanitized
    
    def download_from_gcs_and_upload_to_drive(self, gcs_blob_name: str, title: str) -> Optional[str]:
        """
        Download file from GCS and upload to Google Drive with the podcast title as filename.
        Returns: Google Drive file ID if successful
        """
        try:
            # Get the blob
            blob = self.bucket.blob(gcs_blob_name)
            
            # Get file extension from original file
            file_extension = Path(gcs_blob_name).suffix
            
            # Create sanitized filename
            sanitized_title = self.sanitize_filename(title)
            drive_filename = f"{sanitized_title}{file_extension}"
            
            # Download to temporary file
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_file_path = os.path.join(temp_dir, drive_filename)
            blob.download_to_filename(temp_file_path)
            
            logger.info(f"📥 Downloaded {gcs_blob_name} to temporary file")
            
            # Upload to Google Drive
            file_metadata = {
                'name': drive_filename,
                'parents': [self.settings['drive_folder_id']]
            }
            
            media = MediaFileUpload(temp_file_path, resumable=True)
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink'
            ).execute()
            
            # Clean up temporary file
            os.remove(temp_file_path)
            
            logger.info(f"✅ Uploaded to Google Drive: {file.get('name')}")
            logger.info(f"🔗 Drive link: {file.get('webViewLink')}")
            
            return file.get('id')
            
        except Exception as e:
            logger.error(f"❌ Failed to transfer file from GCS to Drive: {e}")
            return None
    
    def execute_podcast_upload_task(self) -> Dict[str, any]:
        """
        Execute the complete podcast upload task.
        Returns: Dictionary with task results
        """
        logger.info("🚀 Starting podcast upload task...")
        
        result = {
            'success': False,
            'title': None,
            'description': None,
            'output_id': None,
            'gcs_file': None,
            'drive_file_id': None,
            'drive_link': None,
            'error': None
        }
        
        try:
            # Step 1: Get latest podcast info from sheets
            title, description, output_id = self.get_latest_podcast_output()
            result.update({
                'title': title,
                'description': description,
                'output_id': output_id
            })
            
            if not title:
                result['error'] = "No podcast title found in latest output"
                return result
            
            # Step 2: Get latest podcast file from GCS
            gcs_file = self.get_latest_podcast_file_from_gcs()
            result['gcs_file'] = gcs_file
            
            if not gcs_file:
                result['error'] = "No podcast file found in GCS"
                return result
            
            # Step 3: Transfer file from GCS to Google Drive
            drive_file_id = self.download_from_gcs_and_upload_to_drive(gcs_file, title)
            result['drive_file_id'] = drive_file_id
            
            if drive_file_id:
                # Get the drive link
                file_info = self.drive_service.files().get(
                    fileId=drive_file_id,
                    fields='webViewLink'
                ).execute()
                result['drive_link'] = file_info.get('webViewLink')
                result['success'] = True
                
                logger.info("✅ Podcast upload task completed successfully!")
            else:
                result['error'] = "Failed to upload file to Google Drive"
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Podcast upload task failed: {e}")
        
        return result
    
    def handle_message(self, message: str) -> str:
        """
        Handle incoming messages and execute appropriate tasks.
        """
        message_lower = message.lower().strip()
        
        if any(keyword in message_lower for keyword in ['upload', 'podcast', 'latest', 'copy', 'transfer']):
            logger.info(f"📨 Received podcast upload request: {message}")
            
            result = self.execute_podcast_upload_task()
            
            if result['success']:
                response = f"✅ Successfully uploaded podcast!\n\n"
                response += f"**Title:** {result['title']}\n"
                response += f"**Output ID:** {result['output_id']}\n"
                response += f"**Source:** {result['gcs_file']}\n"
                response += f"**Drive Link:** {result['drive_link']}\n"
                
                if result['description']:
                    response += f"**Description:** {result['description'][:200]}{'...' if len(result['description']) > 200 else ''}\n"
                
                return response
            else:
                return f"❌ Failed to upload podcast: {result['error']}"
        
        elif any(keyword in message_lower for keyword in ['help', 'commands', 'what can you do']):
            return self.get_help_message()
        
        else:
            return "I can help you upload the latest podcast to Google Drive. Try saying 'upload latest podcast' or 'help' for more options."
    
    def get_help_message(self) -> str:
        """Get help message with available commands."""
        return """
🤖 **AI Podcast Agent Commands:**

• `upload latest podcast` - Find latest podcast output and upload to Google Drive
• `transfer podcast` - Same as above
• `help` - Show this help message

**What I do:**
1. 📊 Check your Google Sheets for the latest podcast output
2. 🎵 Find the latest audio file in Google Cloud Storage
3. 📁 Upload it to your Google Drive folder with the podcast title as filename
4. 🔗 Provide you with the shareable Drive link

**Current Settings:**
• Drive Folder: https://drive.google.com/drive/folders/13G1L2HSLwdPJHuUoKT0DT8j1IiqHpm8u
• GCS Source: jmio-podcast-storage/podcasts/
• Supported formats: MP3, WAV, M4A
        """.strip()

def main():
    """Main function for testing the agent."""
    try:
        agent = PodcastAgent()
        
        print("🤖 AI Podcast Agent initialized successfully!")
        print("Type 'help' for commands or 'upload latest podcast' to test.")
        print("Type 'quit' to exit.\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    print("👋 Goodbye!")
                    break
                
                if user_input:
                    response = agent.handle_message(user_input)
                    print(f"\nAgent: {response}\n")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")

if __name__ == "__main__":
    main() 