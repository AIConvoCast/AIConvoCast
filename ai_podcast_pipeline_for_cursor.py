import os
import pandas as pd
import gspread
import requests
import openai
from openai import OpenAI
from pydub import AudioSegment
from dotenv import load_dotenv
import time
import re
import io
import tempfile
import traceback
import json
import sys
import shutil
from pathlib import Path
from google.oauth2.service_account import Credentials
import xml.etree.ElementTree as ET
import html
import warnings
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from google.cloud import storage
print(storage.__version__)

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# GOOGLE CLOUD STORAGE CONFIGURATION
# -----------------------------------------
GCS_BUCKET_NAME = 'jmio-podcast-storage'  # Replace with your bucket name
GCS_SERVICE_ACCOUNT_FILE = 'jmio-google-api.json'  # Your existing service account key file

def get_gcs_client():
    """Initialize and return a Google Cloud Storage client."""
    try:
        client = storage.Client.from_service_account_json(GCS_SERVICE_ACCOUNT_FILE)
        return client
    except Exception as e:
        print(f"❌ Error initializing GCS client: {e}")
        return None

def upload_file_to_gcs(file_path, destination_blob_name):
    """Upload a file to Google Cloud Storage and return the public URL."""
    try:
        client = get_gcs_client()
        if not client:
            return None
            
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(destination_blob_name)
        
        blob.upload_from_filename(file_path)
        
        # For uniform bucket-level access, we don't need to make individual objects public
        # The bucket's IAM permissions control access
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{destination_blob_name}"
    except Exception as e:
        print(f"❌ Error uploading to GCS: {e}")
        return None

def download_file_from_gcs(blob_name, local_file_path):
    """Download a file from Google Cloud Storage."""
    try:
        client = get_gcs_client()
        if not client:
            return None
            
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        blob.download_to_filename(local_file_path)
        return local_file_path
    except Exception as e:
        print(f"❌ Error downloading from GCS: {e}")
        return None

def list_files_in_gcs_folder(folder_prefix):
    """List files in a GCS folder (prefix)."""
    try:
        client = get_gcs_client()
        if not client:
            return []
            
        bucket = client.bucket(GCS_BUCKET_NAME)
        blobs = bucket.list_blobs(prefix=folder_prefix)
        
        return [blob.name for blob in blobs]
    except Exception as e:
        print(f"❌ Error listing GCS files: {e}")
        return []

def get_latest_file_in_gcs_folder(folder_prefix):
    """Get the latest file in a GCS folder based on creation time."""
    try:
        client = get_gcs_client()
        if not client:
            return None
            
        bucket = client.bucket(GCS_BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=folder_prefix))
        
        if not blobs:
            return None
            
        # Sort by creation time (newest first)
        latest_blob = max(blobs, key=lambda x: x.time_created)
        return latest_blob.name
    except Exception as e:
        print(f"❌ Error getting latest file from GCS: {e}")
        return None

def download_latest_text_file_from_gcs(folder_prefix):
    """Downloads the latest text file from a Google Cloud Storage folder."""
    try:
        latest_file = get_latest_file_in_gcs_folder(folder_prefix)
        if not latest_file:
            print(f"❌ No text files found in folder {folder_prefix}")
            return None
            
        # Download to temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_{os.path.basename(latest_file)}"
        result = download_file_from_gcs(latest_file, temp_path)
        
        if result:
            # Read the text content with UTF-8 encoding
            try:
                with open(temp_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Fallback: try to detect encoding
                import chardet
                with open(temp_path, 'rb') as f:
                    raw_data = f.read()
                    detected = chardet.detect(raw_data)
                    encoding = detected['encoding'] or 'utf-8'
                    print(f"⚠️ UTF-8 decode failed, detected encoding: {encoding}")
                    content = raw_data.decode(encoding, errors='replace')
            
            # Clean up temp file
            try:
                os.remove(temp_path)
            except:
                pass
                
            print(f"✅ Downloaded {len(content)} characters from {latest_file}")
            return content
        else:
            return None
        
    except Exception as e:
        print(f"❌ Error downloading text file from GCS: {e}")
        return None

def upload_audio_to_gcs(audio_file_path, destination_blob_name):
    """Uploads an audio file to Google Cloud Storage and returns the public URL."""
    return upload_file_to_gcs(audio_file_path, destination_blob_name)

def download_latest_mp3_from_gcs(folder_prefix):
    """Downloads the latest MP3 file from a Google Cloud Storage folder."""
    try:
        latest_file = get_latest_file_in_gcs_folder(folder_prefix)
        if not latest_file:
            print(f"❌ No MP3 files found in folder {folder_prefix}")
            return None
            
        # Download to temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_{os.path.basename(latest_file)}"
        result = download_file_from_gcs(latest_file, temp_path)
        
        if result:
            print(f"✅ Downloaded MP3 file: {temp_path}")
            return temp_path
        else:
            return None
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from GCS: {e}")
        return None

def download_mp3_file_from_gcs(blob_name):
    """Downloads a specific MP3 file from Google Cloud Storage."""
    try:
        # Download to temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_{os.path.basename(blob_name)}"
        result = download_file_from_gcs(blob_name, temp_path)
        
        if result:
            print(f"✅ Downloaded MP3 file: {temp_path}")
            return temp_path
        else:
            return None
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from GCS: {e}")
        return None

def upload_text_to_gcs(text_content, destination_blob_name):
    """Uploads text content to Google Cloud Storage and returns the public URL."""
    try:
        # Ensure text content is properly encoded as UTF-8
        if isinstance(text_content, bytes):
            text_content = text_content.decode('utf-8')
        elif not isinstance(text_content, str):
            text_content = str(text_content)

        # Apply encoding fix before saving
        text_content = fix_text_encoding(text_content)

        # FINAL CHECK: Force clean all mojibake and print debug info
        before = text_content[:200]
        text_content = force_clean_mojibake(text_content)
        after = text_content[:200]
        if 'â€™' in before:
            print("❗ force_clean_mojibake applied before saving to GCS")
            print(f"Before: {before}")
            print(f"After:  {after}")

        # Create temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_text_{int(time.time())}.txt"
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(text_content)

        # Upload to GCS
        result = upload_file_to_gcs(temp_path, destination_blob_name)

        # Clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass

        return result

    except Exception as e:
        print(f"❌ Error uploading text to GCS: {e}")
        return None

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'jmio-google-api.json'
GOOGLE_SHEET_NAME = 'AI Workflow'
GOOGLE_DRIVE_FOLDER_ID = '17XAnga8MC1o23rFhiQ7fcrrqDNhz_-oB'  # Folder to create the sheet in
SHARE_SHEET_WITH_EMAIL = 'AIConvoCast@gmail.com'

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')

# Instantiate the OpenAI client once using the API key from environment variables
if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY is not set in environment variables")
    print("Please ensure OPENAI_API_KEY is set in your GitHub environment variables")
    sys.exit(1)

if not ELEVENLABS_API_KEY:
    print("❌ ELEVENLABS_API_KEY is not set in environment variables")
    print("Please ensure ELEVENLABS_API_KEY is set in your GitHub environment variables")
    sys.exit(1)

print(f"✅ OpenAI API Key configured (length: {len(OPENAI_API_KEY)})")
print(f"✅ Eleven Labs API Key configured (length: {len(ELEVENLABS_API_KEY)})")

client = OpenAI(api_key=OPENAI_API_KEY)

print(f"[DEBUG] Python version: {sys.version}")
print(f"[DEBUG] requests version: {requests.__version__}")
try:
    import elevenlabs
    print(f"[DEBUG] elevenlabs version: {elevenlabs.__version__}")
except ImportError:
    pass

# Set the directory for generated mp3 files
MP3_OUTPUT_DIR = Path("generated_mp3")
MP3_OUTPUT_DIR.mkdir(exist_ok=True)

# Clean up old mp3 files (older than 5 days)
def cleanup_old_mp3_files():
    now = time.time()
    cutoff = now - 5 * 24 * 60 * 60  # 5 days in seconds
    for mp3_file in MP3_OUTPUT_DIR.glob("*.mp3"):
        if mp3_file.is_file() and mp3_file.stat().st_mtime < cutoff:
            print(f"[CLEANUP] Deleting old mp3 file: {mp3_file}")
            try:
                mp3_file.unlink()
            except Exception as e:
                print(f"[CLEANUP ERROR] Could not delete {mp3_file}: {e}")

# Call cleanup at the start of the script
cleanup_old_mp3_files()

# -----------------------------------------
# GOOGLE DRIVE OAUTH AUTHENTICATION (KEPT FOR REFERENCE - NOT USED WITH GCS)
# -----------------------------------------
def get_drive_service_oauth():
    """Authenticate as the user via OAuth and return a Drive service object."""
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('drive', 'v3', credentials=creds)
    return service

# -----------------------------------------
# GOOGLE SHEET SUPPORT
# -----------------------------------------
def create_and_setup_google_sheet(gc, sheet_name, folder_id, user_email):
    """Creates and populates a new Google Sheet with the required structure."""
    print(f"✨ Creating new Google Sheet '{sheet_name}'...")
    spreadsheet = gc.create(sheet_name, folder_id=folder_id)
    spreadsheet.share(user_email, perm_type='user', role='writer')

    template_dfs = get_template_dataframes()
    sheet_order = ["Workflows", "Outputs", "Requests", "Prompts", "Models", "Workflow Steps", "Locations", "Eleven"]

    # Rename the initial "Sheet1" and populate it
    ws = spreadsheet.worksheet("Sheet1")
    ws.update_title(sheet_order[0])
    df = template_dfs.get(sheet_order[0])
    ws.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"  - Created and formatted sheet: {sheet_order[0]}")

    # Add and populate the remaining sheets in the correct order
    for title in sheet_order[1:]:
        df = template_dfs.get(title)
        if df is not None:
            ws = spreadsheet.add_worksheet(title=title, rows=100, cols=30)
            ws.update([df.columns.values.tolist()] + df.values.tolist())
            print(f"  - Created and formatted sheet: {title}")

    print(f"✅ Google Sheet created and shared with {user_email}.")
    return spreadsheet


def connect_to_google_sheet_with_retry(retries=5, delay=10):
    for attempt in range(retries):
        try:
            creds = Credentials.from_service_account_file(GOOGLE_CREDS_JSON, scopes=[
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ])
            gc = gspread.authorize(creds)
            return gc
        except gspread.exceptions.APIError as e:
            print(f"Google Sheets API error: {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds... (Attempt {attempt+1}/{retries})")
                time.sleep(delay)
            else:
                print("Max retries reached. Exiting.")
                raise

def try_load_google_sheet():
    try:
        gc = connect_to_google_sheet_with_retry()
        try:
            spreadsheet = gc.open(GOOGLE_SHEET_NAME)
            ws = spreadsheet.worksheet("Workflows")
            headers = ws.row_values(1)
            if "Workflow Code" not in headers:
                print("⚠️ Old sheet structure detected. Archiving and creating a new one.")
                archive_name = f"{GOOGLE_SHEET_NAME} (Archived {int(time.time())})"
                gc.rename(spreadsheet, archive_name)
                print(f"  - Old sheet renamed to '{archive_name}'")
                spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)
        except gspread.exceptions.SpreadsheetNotFound:
            spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)
        return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in spreadsheet.worksheets()}
    except Exception as e:
        print(f"❌ Google Sheets not accessible: {e}")
        return None

# -----------------------------------------
# EXCEL FALLBACK STRUCTURE
# -----------------------------------------
def get_template_dataframes():
    """Returns a dictionary of DataFrames for the new simplified template structure."""
    workflow = pd.DataFrame([
        [1, "Generate Daily Script", "P1,P2&R1,P3&R2", "gpt-4o"],
        [2, "Test Daily News", "P1", "gpt-4o"],
        [3, "Test Daily News", "P1", "gpt-4o-mini"],
        [4, "Test Daily News", "P1M4", ""],
        [5, "Test Daily News", "P1M2", ""],
        [6, "Test Daily News", "P1M2,P2&R1M4", ""],
        [7, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2", ""],
        [8, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2,P4&R3M3", ""],
        [9, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2,P4&R3M3,P5&R4M3", ""],
        [10, "Test Daily News and Script Save", "P1M2,P6&R1M2,P3&R2M2,P4&R3M3,P5&R4M3,R4SL7", ""],
        [11, "Send latest script to Eleven Labs", "L8E1SL4", ""],
        [12, "Combine intro mp3 with latest mp3 with outro mp3", "L1&L9&L2SL3", ""],
        [13, "Generates Script, Sends to EL and Comines", "P1M2,P6&R1M2,P3&R2M2,P4&R3M3,P5&R4M3,R4SL7,L8E1SL4,L1&L9&L2SL3", ""],
        [14, "Good Daily News and Script Save", "P1M1,P6&R1M1,P3&R2M1,P4&R3M18,P5&R4M3,R4SL7", ""],
        [15, "Send to Eleven and Combine", "L8E1SL4,L1&L9&L2SL3", ""],
        [16, "Good Daily News, Send to Eleven and Combine", "P1M1,P6&R1M1,P3&R2M1,P4&R3M18,P5&R4M3,R4SL7,L8E1SL4,L1&L9&L2SL3", ""],
        [17, "Top 5 Daily AI News, Send to Eleven and Combine", "P1M1,P7&R1M1,P3&R2M1,P4&R3M18,P5&R4M3,R4SL7,L8E1SL4,L1&L9&L2SL3", ""],
        [18, "Posted Podcasts Update", "PPU", ""],
        [19, "Retrieve the last 5 title and descriptions from Posted Podcasts", "PPL5", ""]
    ], columns=["Workflow ID", "Workflow Title", "Workflow Code", "Model Default"])

    outputs = pd.DataFrame(columns=[
        "Output ID", "Triggered Date",
        *[f"Output {i}" for i in range(1, 26)]
    ])

    requests = pd.DataFrame([
        [1, 1, '', 'N', ''],
        [2, 2, '', 'N', ''],
        [3, 3, '', 'N', ''],
        [4, 4, '', 'N', ''],
        [5, 5, '', 'N', ''],
        [6, 6, '', 'N', ''],
        [7, 7, '', 'N', ''],
        [8, 8, '', 'N', ''],
        [9, 9, '', 'N', ''],
        [10, 10, '', 'N', 'Generates and outputs to scripts folder'],
        [11, 11, '', 'N', 'Generates eleven labs based on latest script saved'],
        [12, 12, '', 'N', 'Combines Intro Mp3 with latest Eleven Labs Mp3 with Outro Mp3 and saves to Podcast folder'],
        [13, 13, '', 'N', 'Generates Script, Sends to EL and Combines'],
        [14, 14, '', 'N', ''],
        [15, 15, '', 'N', 'Sends to eleven and combines'],
        [16, 16, '', 'N', 'Top 3 News Stories'],
        [17, 17, '', 'N', 'Top 5 News Stories'],
        [18, 18, '', 'Y', 'Posted Podcasts Tab Update'],
        [19, 19, '', 'N', 'Run workflow to test getting the title and description from the last 5 posted podcasts']
    ], columns=["Request ID", "Workflow ID", "Custom Topic If Required", "Active", "Comments"])

    prompts = pd.DataFrame([
        [1, "Daily News", "Please provide a comprehensive overview of the most important news in AI that occurred in the last 24-48 hours and mention dates of when the news items or recent updates occurred to confirm occurrence in the last 24-48 hours. AI news can be in relation to AI model releases, Expected tool releases, New enhancements released for AI tools or other interesting topics related to AI technology, AI company announcements, models, tool releases, enhancements, etc. Please be sure to summarize as many sources as possible and also provide numerous quotes from both company representatives, reporters as well as user feedback on social media."],
        [2, "Top 3 Topics", "Please select the best 3 news stories to include in an AI Techology news podcast episodes. The 3 news stories selected should be the whatever news stories you believe are the most interesting and will be most compelling and interesting to our AI Podcast listeners. The 8 possible new items to choose from are below. Please select the top 3 and provide the exact text of the new items provided below:"],
        [3, "Generate All On Appendend Topic", "Generate all details related to the news stories below from the last 24-48 hours. Please make sure to include any and all quotes from participants, companies or even social media reactions that have received significant engagement. Please also include technical specifications if required. Please ensure complete coverage provided  details to ensure comprehensive coverage of story. Stories to retrieve all relevant details on:"],
        [4, "Create Script Based on Material", '''Create a podcast script for the "AI Convo Cast" podcast, which is a daily AI news and technology podcast. We will be adding a standard intro and outro to the podcast script you provide on our end, so only generate the main body of the episode script and always start with:
"Today we will be..."
Since we will add intro and outro on our end, please do not make references to the podcast, simply generate the script going over the topics provided along with a very brief and positive 1 sentence summary of topics covered. The script should be written in plain, conversational language that is casual, concise and assumes the listener is familiar with AI model generally and just wants to hear the facts. Use quotes from company representatives when possible. Design the content for a natural 15-minute runtime with smooth transitions and integrated summary breakpoints (without explicit headings or titles) that lead into a high-level, abstract summary tying together broader implications, but leaning towards a positive perspective on the AI's advancement and an eagerness to embrace it. Podcast script should contain between 4,750 and 7,000 characters.
Output must be pure plain text (UTF‑8 encoded) with no hyperlinks, citations, markdown formatting, extraneous symbols, or any headings like "Summary." Do not include any non-text elements or words/phrases ending in ".com." Adjust tone, style, or content as clarified by the user while always prioritizing a clean, accessible, and entertaining spoken presentation. Avoid numbering or bullet points and refrain from using corny sayings. Please also always remove dashes from names (e.g. GPT-4.5 should be GPT 4.5). When converting this text to speech, automatically replace 'GPT 4o' with 'GPT Four-Oh', 'DALL-E' with 'Dolly'. Avoid corny transitions like "speaking of". Transitions should be smooth or simply go into next topic.

Podcast Material for to Base Script On:'''],
        [5, "Generate Title and Description", '''Please generate a podcast title and description based on the topic or podcast script provided after "Topic to generate Title and Description based" below. The Podcast title and Description should be generated in a similar tone and style as the 3 examples below. Please try to include the specific companies in the titles in order to help those searching for news on those companies. That said only list 2-3 names max to keep the title as brief as possible. Please avoid using phrases with colons as well.

Please always include Amazon an Affiliate Link to this exact address and say "Help support the podcast by using our affiliate links:
Eleven Labs: https://try.elevenlabs.io/ibl30sgkibkv"

The end of the description should also always include a disclaimer to indicate the podcast is purely for informational purposes and include disclaimer for affiliate links. Do not include text images, bullets or numbering for subsections to avoid compatibility issues, only text. Never reference a particular time or date in the title to ensure podcasts remain evergreen. Ensure the title and description provide an overview of the topics included and the specific technology or companies involved in order to increase engagement and SEO.

Front-load important keywords and topics in the first 1-2 sentences of the description. For example, begin with "In this episode, we discuss [XYZ]…". Include relevant AI terms, guest names, and company names that relate to the episode. Keep the description concise, 3-4 sentences is ideal. If your episode touches on, say, "OpenAI's latest model release and Google's AI announcement," make sure those phrases appear in the description. Reuse keywords around 5 times in your show's description if feasible.

Example Podcast 1: "Title:
Automate Your Workflow and Podcast with AI
Description:
Discover the power of AI-driven automation to streamline your podcasting process and boost your efficiency. In this episode, we explore how tools like Zapier and Google's Notebook LM can revolutionize your content creation workflow. Learn how to automate tasks such as generating episode titles and descriptions, creating engaging scripts from blog posts or videos, and designing eye-catching cover art with AI image tools like DALL-E and Midjourney. We also dive into no-code automation platforms like Make.com, showing you how to seamlessly integrate AI into your podcasting routine.

Help support the podcast by using our Affiliate Links:
Eleven Labs: https://try.elevenlabs.io/ibl30sgkibkv

Disclaimer:
This podcast is an independent production and is not affiliated with, endorsed by, or sponsored by Zapier, Google, OpenAI, DALL-E, Midjourney, Make.com, or any other entities mentioned unless explicitly mentioned. The content provided is for educational and entertainment purposes only and does not constitute professional or technical advice. All trademarks, logos, and copyrights mentioned are the property of their respective owners."

Example Podcast 2: "Title:
AI's Next Leap: Meta's $65B Bet, Agentic AI, and the Future of Automation

Description:
In this episode, we break down the latest AI trends, including Meta's massive $65 billion AI infrastructure push, the rise of "agentic AI" capable of autonomous task execution, and new, more efficient AI models reshaping the industry. We also examine the ethical dilemmas surrounding deepfake legislation, copyright lawsuits, and the impact of AI automation on the workforce. From NVIDIA's latest Blackwell architecture to Amazon's Nova models and Google's Gemini 2.0, we analyze how AI is evolving beyond theoretical capabilities into real-world applications.

Help support the podcast by using our affiliate links:
Eleven Labs: https://try.elevenlabs.io/ibl30sgkibkv

Disclaimer:
This podcast is an independent production and is not affiliated with, endorsed by, or sponsored by Meta, NVIDIA, Amazon, Google,  or any other entities mentioned unless explicitly mentioned. The content provided is for educational and entertainment purposes only and does not constitute professional, financial, or legal advice."

Example Podcast 3: "Title:
Bought a Website? How to Setup Domains, Hosting, and SEO
Description:
Overview of setting up a website with Namecheap after you've purchased it. From registering a domain and choosing the right hosting plan to building your site with Namecheap's Website Builder or WordPress, we walk through the essential steps to get your online presence up and running.
Discover the key differences between website builders and web hosting, how to navigate Namecheap's user-friendly tools like cPanel and Softaculous, and crucial post-setup tasks such as SSL security, professional email setup, and SEO optimization. We also cover cost-saving strategies, security best practices, and expert tips to streamline the process. Whether you're a beginner looking for a simple drag-and-drop solution or an advanced user preferring manual HTML and FTP uploads, Namecheap offers a range of flexible options to fit your needs.

Help support the podcast by using our affiliate links:
Eleven Labs: https://try.elevenlabs.io/ibl30sgkibkv

Disclaimer:
This podcast is an independent production and is not affiliated with, endorsed by, or sponsored by Namecheap or any other entities mentioned unless explicitly mentioned. This episode was generated using AI tools for entertainment purposes only."

Topic to generate Title and Description based:'''],
        [6, "Top 3 Topics and Validate", "Please select the top 3 news stories to include in an AI Techology news podcast episodes. The 3 news stories selected should be the whatever news stories you believe are the most interesting and will be most compelling and interesting to our AI Podcast listeners. The 8 possible new items to choose from are below. Please select the top 3 and provide the exact text of the new items provided below. Please also validate that the news item has recently ocurred and provide any additional context you can find through web search along with the news story:"],
        [7, "Top 5 Topics and Validate", "Please select the top 5 news stories to include in an AI Techology news podcast episodes. The 5 news stories selected should be the whatever news stories you believe are the most interesting and will be most compelling and interesting to our AI Podcast listeners. The 8 possible news items to choose from are below. Please select the best 5 and provide the exact text of the news items provided below. Please also validate that the news item has recently ocurred and provide any additional context you can find through web search along with the news story:"],
        [8, "Do not select topics previously covered", "Please ensure news items selected do not exactly cover topics previously discuss below. Updates to these new items should still be included. Previously Covered News Items to avoid unless it is an an update on previously covered story:"]
    ], columns=["Prompt ID", "Prompt Title", "Prompt Description"])

    models = pd.DataFrame([
        [1, "gpt-4o", "N", "Y"],
        [2, "gpt-4o-mini", "N", "Y"],
        [3, "gpt-4o", "N", "N"],
        [4, "gpt-4o-mini", "Y", "N"],
        [5, "gpt-4o-mini-search-preview", "N", "Y"],
        [6, "gpt-4o-search-preview", "N", "Y"],
        [7, "chatgpt-4o-latest", "N", "N"],
        [8, "codex-mini-latest", "N", "N"],
        [9, "dall-e-2", "N", "N"],
        [10, "dall-e-3", "N", "N"],
        [11, "gpt-3.5-turbo-instruct", "N", "N"],
        [12, "gpt-4", "N", "N"],
        [13, "gpt-4.1", "N", "N"],
        [14, "gpt-4.1-mini", "N", "N"],
        [15, "gpt-4.1-mini-2025-04-14", "N", "N"],
        [16, "gpt-4.1-nano", "N", "N"],
        [17, "gpt-4.1-nano-2025-04-14", "N", "N"],
        [18, "gpt-4.5-preview", "N", "N"],
        [19, "gpt-4.5-preview-2025-02-27", "N", "N"],
        [20, "gpt-4o-audio-preview", "N", "N"],
        [21, "gpt-4o-mini-audio-preview", "N", "N"],
        [22, "gpt-4o-mini-search-preview", "N", "N"],
        [23, "gpt-4o-mini-search-preview-2025-03-11", "N", "N"],
        [24, "gpt-4o-mini-transcribe", "N", "N"],
        [25, "gpt-4o-mini-tts", "N", "N"],
        [26, "gpt-4o-realtime-preview", "N", "N"],
        [27, "gpt-4o-search-preview", "N", "N"],
        [28, "gpt-4o-search-preview-2025-03-11", "N", "N"],
        [29, "gpt-4o-transcribe", "N", "N"],
        [30, "gpt-image-1", "N", "N"],
        [31, "o1", "N", "N"],
        [32, "o1-mini", "N", "N"],
        [33, "o1-preview", "N", "N"],
        [34, "o1-pro", "N", "N"],
        [35, "o3-mini", "N", "N"],
        [36, "o3-mini-2025-01-31", "N", "N"],
        [37, "o4-mini", "N", "N"],
        [38, "omni-moderation-latest", "N", "N"],
        [39, "text-embedding-3-large", "N", "N"],
        [40, "text-embedding-3-small", "N", "N"],
        [41, "tts-1", "N", "N"],
        [42, "tts-1-1106", "N", "N"],
        [43, "tts-1-hd", "N", "N"],
        [44, "whisper-1", "N", "N"]
    ], columns=["Model ID", "Model Name", "Model Default", "Web Search"])

    workflow_steps = pd.DataFrame(columns=[
        "Workflow Steps ID", "Triggered Date", "Workflow ID", "Request ID", "Workflow Steps All", "Workflow Step", "Input", "Output", "Log Messages"
    ])

    locations = pd.DataFrame([
        [1, "Intro MP3 File", "File", "Intro.mp3", "Intro.mp3"],
        [2, "Outro MP3 File", "File", "Outro.mp3", "Outro.mp3"],
        [3, "Podcast Folder Location", "Folder", "podcasts/", "podcasts/"],
        [4, "Eleven Labs Generated Audio", "Folder", "eleven-labs/", "eleven-labs/"],
        [5, "Latest MP3 File in Folder", "mp3", "podcasts/", "podcasts/"],
        [6, "Latest MP3 File in Folder", "mp3", "eleven-labs/", "eleven-labs/"],
        [7, "Scripts Folder Location", "Folder", "scripts/", "scripts/"],
        [8, "Latest Text File in Scripts Folder", "Text", "scripts/", "scripts/", "Y"],
        [9, "Latest mp3 in Eleven lab Folder", "mp3", "eleven-labs/", "eleven-labs/", "Y"]
    ], columns=["Location ID", "Location Description", "Type", "File Or Folder", "Location", "Latest"])

    eleven = pd.DataFrame([
        [1, "Liam", "eleven_multilingual_v2", 0.39, 0.7, 0.5, 1.06]
    ], columns=["Eleven ID", "Voice", "Model", "Stability", "Similarity Boost", "Style", "Speed"])

    return {
        "Workflows": workflow,
        "Outputs": outputs,
        "Requests": requests,
        "Prompts": prompts,
        "Models": models,
        "Workflow Steps": workflow_steps,
        "Locations": locations,
        "Eleven": eleven
    }


def generate_excel_template(file_path):
    template_dfs = get_template_dataframes()
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        for sheet_name, df in template_dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"✅ Excel template created at: {file_path}")

# -----------------------------------------
# DATA LOADING FROM FILE OR GOOGLE
# -----------------------------------------
def load_workbook():
    data = try_load_google_sheet()
    if data:
        return data
    print("❌ Google Sheets not accessible. Please check your credentials, network, or sharing settings.")
    exit(1)

# -----------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------
def get_model_for_step(row, step_key, settings_df):
    override = row.get(f"Model: {step_key}")
    if override and str(override).strip():
        return override.strip()
    setting_map = {
        "Story Selection": "default_model_story_select",
        "Research": "default_model_research",
        "Script Gen": "default_model_script",
        "Title Desc": "default_model_title_desc"
    }
    setting_key = setting_map.get(step_key)
    value = settings_df.loc[settings_df['Setting Key'] == setting_key, 'Value']
    return value.values[0] if not value.empty else None

def get_intro_outro_paths(row, settings_df):
    base_path = settings_df.loc[settings_df['Setting Key'] == 'base_audio_folder_path', 'Value'].values[0]
    intro_file = row.get('Intro File Name') or settings_df.loc[settings_df['Setting Key'] == 'default_intro_file', 'Value'].values[0]
    outro_file = row.get('Outro File Name') or settings_df.loc[settings_df['Setting Key'] == 'default_outro_file', 'Value'].values[0]
    return os.path.join(base_path, intro_file), os.path.join(base_path, outro_file)

def fix_text_encoding(text):
    """Fix common encoding issues in text, particularly mojibake characters."""
    if not isinstance(text, str):
        return str(text)
    
    # Check for mojibake characters
    if 'â€™' in text or 'â€œ' in text or 'â€' in text:
        print(f"⚠️  ENCODING ISSUE DETECTED in text!")
        print(f"Original text sample: {text[:200]}...")
        
        try:
            # Common mojibake fix: encode as latin1, decode as utf-8
            fixed_text = text.encode('latin1').decode('utf-8')
            print(f"Fixed text sample: {fixed_text[:200]}...")
            return fixed_text
        except Exception as e:
            print(f"Failed to fix encoding with latin1 method: {e}")
            
            try:
                # Alternative fix: replace common mojibake patterns
                replacements = {
                    'â€™': "'",
                    'â€œ': '"',
                    'â€': '"',
                    'â€"': '—',
                    'â€¦': '…',
                    'â€¢': '•',
                    'â€"': '–',
                    'â€˜': "'",
                    'â€™': "'",
                    'â€œ': '"',
                    'â€': '"'
                }
                fixed_text = text
                for mojibake, correct in replacements.items():
                    fixed_text = fixed_text.replace(mojibake, correct)
                print(f"Fixed text with replacements sample: {fixed_text[:200]}...")
                return fixed_text
            except Exception as e2:
                print(f"Failed to fix encoding with replacements: {e2}")
                return text
    
    return text

def force_clean_mojibake(text):
    """Force replace all known mojibake patterns with correct characters."""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        'â€™': "'",
        'â€œ': '"',
        'â€': '"',
        'â€"': '—',
        'â€¦': '…',
        'â€¢': '•',
        'â€"': '–',
        'â€˜': "'",
        'Ã©': 'é',
        'Ã': 'à',
        'Â': '',  # Sometimes appears as a stray
        'â€™': "'",  # Ian added 
    }
    for mojibake, correct in replacements.items():
        text = text.replace(mojibake, correct)
    return text

# -----------------------------------------
# API CALLS
# -----------------------------------------
def call_openai_model(prompt, model="gpt-4o", temperature=0.7, web_search=False):
    """Calls the OpenAI API, using the correct endpoint for web search and model type. Logs all errors and unexpected responses."""
    import sys
    if not client.api_key:
        msg = "❌ OpenAI API key is not configured. Please check your .env file."
        log_error(msg)
        sys.exit(1)
    try:
        # Case 1: Chat Completions with always-on search-preview model
        if web_search and (model.endswith("-search-preview")):
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                web_search_options={
                    "user_location": {"type": "approximate", "approximate": {"country": "US"}},
                    "search_context_size": "high"
                },
                temperature=temperature
            )
            # Robust error logging for chat completions
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI ChatCompletions error: {response.error}\nFull response: {response}")
                sys.exit(1)
            if hasattr(response, 'choices') and response.choices:
                raw_response = response.choices[0].message.content.strip()
                return fix_text_encoding(raw_response)
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            sys.exit(1)
        # Case 2: Responses API with web_search_preview tool (base models)
        elif web_search:
            if not hasattr(client, 'responses'):
                msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                log_error(msg)
                sys.exit(1)
            response = client.responses.create(
                model=model,
                tools=[{"type": "web_search_preview",
                        "search_context_size": "high",
                        "user_location": {"type": "approximate", "country": "US"}}],
                input=[{"role": "user",
                        "content": [{"type": "input_text", "text": prompt}]}],
                text={"format": {"type": "text"}}
            )
            # Robust error logging for responses.create
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI Responses error: {response.error}\nFull response: {response}")
                sys.exit(1)
            try:
                for msg in getattr(response, 'output', []):
                    # Handle both dict and object
                    role = getattr(msg, 'role', None) or (msg.get('role') if isinstance(msg, dict) else None)
                    if role == "assistant":
                        content_list = getattr(msg, 'content', None) or (msg.get('content') if isinstance(msg, dict) else None)
                        if content_list:
                            for content in content_list:
                                # Handle both object and dict
                                ctype = getattr(content, 'type', None) or (content.get('type') if isinstance(content, dict) else None)
                                text = getattr(content, 'text', None) or (content.get('text') if isinstance(content, dict) else None)
                                if ctype == "output_text" and text:
                                    return fix_text_encoding(text.strip())
                log_error(f"OpenAI Responses: Unexpected empty or malformed response. Full response: {response}")
                sys.exit(1)
            except Exception as e:
                log_error(f"Error parsing OpenAI web search response: {e}\nRaw response: {response}")
                sys.exit(1)
        # Case 3: Standard Chat Completions
        else:
            # Always omit temperature for o4-mini and similar models
            models_without_temp = {"o4-mini", "o4-mini-2025-01-31"}
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}]
            }
            if model not in models_without_temp and temperature is not None:
                kwargs["temperature"] = temperature
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as e:
                error_msg = str(e)
                # If this is o4-mini or similar, exit immediately
                if model in models_without_temp:
                    log_error(f"OpenAI error for model {model}: {e}")
                    sys.exit(1)
                # For other models, try retrying without temperature if error is about temperature
                if ("'temperature' does not support" in error_msg or "unsupported_value" in error_msg) and "temperature" in kwargs:
                    log_error(f"Retrying OpenAI call for model {model} without temperature due to error: {error_msg}")
                    del kwargs["temperature"]
                    try:
                        response = client.chat.completions.create(**kwargs)
                    except Exception as e2:
                        log_error(f"OpenAI error after retrying without temperature: {e2}")
                        sys.exit(1)
                else:
                    log_error(f"OpenAI error: {e}")
                    sys.exit(1)
            # Robust error logging for chat completions
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI ChatCompletions error: {response.error}\nFull response: {response}")
                sys.exit(1)
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content.strip()
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            sys.exit(1)
    except Exception as e:
        log_error(f"OpenAI error: {e}")
        sys.exit(1)

def split_text_into_chunks(text, max_length=2500):
    """
    Splits text into chunks of up to max_length characters, preferably on sentence boundaries.
    If a sentence is longer than max_length, it is split into hard chunks.
    """
    import re
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ''
    for sentence in sentences:
        # If the sentence itself is too long, split it hard
        while len(sentence) > max_length:
            part = sentence[:max_length]
            sentence = sentence[max_length:]
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ''
            chunks.append(part)
        if len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += (' ' if current_chunk else '') + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    print(f"[DEBUG] split_text_into_chunks: {len(chunks)} chunk(s) created.")
    for i, chunk in enumerate(chunks):
        print(f"[DEBUG]   Chunk {i+1} length: {len(chunk)}")
    return chunks

def generate_voice_audio(text, voice_id, output_path, eleven_config=None):
    """
    Enhanced Eleven Labs API call using the official Python client.
    Handles chunking for long texts and merges resulting audio files.
    Falls back to REST API if the client fails.
    """
    try:
        from elevenlabs.client import ElevenLabs
        # Split text into <=2500 character chunks
        chunks = split_text_into_chunks(text, max_length=2500)
        print(f"[DEBUG] generate_voice_audio: Preparing to send {len(chunks)} chunk(s) to Eleven Labs API.")
        if len(chunks) == 1:
            chunk_text = chunks[0]
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            if eleven_config:
                voice_settings = {
                    "stability": float(eleven_config.get('Stability', 0.39)),
                    "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                    "style": float(eleven_config.get('Style', 0.5)),
                    "speed": float(eleven_config.get('Speed', 1.06))
                }
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    if len(chunk_text) > 2000:
                        print(f"[WARNING] Chunk is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                    start_time = time.time()
                    audio_stream = client.text_to_speech.convert(
                        text=chunk_text,
                        voice_id=voice_id,
                        voice_settings=voice_settings,
                        model_id=eleven_config.get('Model', 'eleven_multilingual_v2')
                    )
                    elapsed = time.time() - start_time
                    print(f"[DEBUG] ElevenLabs SDK call returned in {elapsed:.3f}s (streaming)")
                    print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk. Saving to file...")
                except Exception as e:
                    print(f"❌ ElevenLabs client error: {e}")
                    traceback.print_exc()
                    print("[DEBUG] Falling back to REST API...")
                    return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
            else:
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    if len(chunk_text) > 2000:
                        print(f"[WARNING] Chunk is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                    start_time = time.time()
                    audio_stream = client.text_to_speech.convert(
                        text=chunk_text,
                        voice_id=voice_id,
                        model_id="eleven_multilingual_v2"
                    )
                    elapsed = time.time() - start_time
                    print(f"[DEBUG] ElevenLabs SDK call returned in {elapsed:.3f}s (streaming)")
                    print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk. Saving to file...")
                except Exception as e:
                    print(f"❌ ElevenLabs client error: {e}")
                    traceback.print_exc()
                    print("[DEBUG] Falling back to REST API...")
                    return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
            with open(output_path, 'wb') as f:
                for chunk in audio_stream:
                    f.write(chunk)
            print(f"✅ Audio generated successfully: {output_path}")
            return output_path
        else:
            # Multiple chunks: process each, then merge
            temp_audio_paths = []
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            for idx, chunk_text in enumerate(chunks):
                temp_path = MP3_OUTPUT_DIR / f"temp_audio_{int(time.time())}_{os.getpid()}_chunk_{idx+1}.mp3"
                print(f"[DEBUG] Sending chunk {idx+1}/{len(chunks)} to Eleven Labs API (length: {len(chunk_text)})")
                print(f"[DEBUG] Chunk {idx+1} preview: {chunk_text[:100]}")
                if eleven_config:
                    voice_settings = {
                        "stability": float(eleven_config.get('Stability', 0.39)),
                        "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                        "style": float(eleven_config.get('Style', 0.5)),
                        "speed": float(eleven_config.get('Speed', 1.06))
                    }
                    try:
                        print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                        if len(chunk_text) > 2000:
                            print(f"[WARNING] Chunk {idx+1} is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                        start_time = time.time()
                        audio_stream = client.text_to_speech.convert(
                            text=chunk_text,
                            voice_id=voice_id,
                            voice_settings=voice_settings,
                            model_id=eleven_config.get('Model', 'eleven_multilingual_v2')
                        )
                        elapsed = time.time() - start_time
                        print(f"[DEBUG] ElevenLabs SDK call for chunk {idx+1} returned in {elapsed:.3f}s (streaming)")
                        print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk {idx+1}. Saving to file {temp_path}...")
                    except Exception as e:
                        print(f"[ERROR] Failed on chunk {idx+1}/{len(chunks)}. First 100 chars: {chunk_text[:100]}")
                        traceback.print_exc()
                        print("[DEBUG] Falling back to REST API...")
                        for p in temp_audio_paths:
                            try: os.remove(p)
                            except: pass
                        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
                else:
                    try:
                        print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                        if len(chunk_text) > 2000:
                            print(f"[WARNING] Chunk {idx+1} is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                        start_time = time.time()
                        audio_stream = client.text_to_speech.convert(
                            text=chunk_text,
                            voice_id=voice_id,
                            model_id="eleven_multilingual_v2"
                        )
                        elapsed = time.time() - start_time
                        print(f"[DEBUG] ElevenLabs SDK call for chunk {idx+1} returned in {elapsed:.3f}s (streaming)")
                        print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk {idx+1}. Saving to file {temp_path}...")
                    except Exception as e:
                        print(f"[ERROR] Failed on chunk {idx+1}/{len(chunks)}. First 100 chars: {chunk_text[:100]}")
                        traceback.print_exc()
                        print("[DEBUG] Falling back to REST API...")
                        for p in temp_audio_paths:
                            try: os.remove(p)
                            except: pass
                        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
                with open(temp_path, 'wb') as f:
                    for chunk in audio_stream:
                        f.write(chunk)
                print(f"✅ Audio chunk {idx+1} generated and saved: {temp_path}")
                temp_audio_paths.append(temp_path)
            # Merge all chunk audio files
            merged_path = MP3_OUTPUT_DIR / f"merged_audio_{int(time.time())}_{os.getpid()}.mp3"
            print(f"[DEBUG] Merging {len(temp_audio_paths)} chunk files into {merged_path}")
            merge_multiple_audio_files(temp_audio_paths, merged_path)
            # Clean up temp chunk files
            for p in temp_audio_paths:
                try: os.remove(p)
                except: pass
            if merged_path and os.path.exists(merged_path):
                print(f"✅ Audio generated and merged successfully: {merged_path}")
            else:
                print(f"❌ Merged audio file {merged_path} was not created!")
            return merged_path
    except ImportError:
        print("⚠️ ElevenLabs Python client not installed. Falling back to REST API...")
        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)


def generate_voice_audio_rest(text, voice_id, output_path, eleven_config=None):
    """Fallback REST API method for Eleven Labs. Handles chunking and merging."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    def _single_chunk(chunk_text, temp_path):
        if eleven_config:
            payload = {
                "text": chunk_text,
                "model_id": eleven_config.get('Model', 'eleven_multilingual_v2'),
                "voice_settings": {
                    "stability": float(eleven_config.get('Stability', 0.39)),
                    "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                    "style": float(eleven_config.get('Style', 0.5)),
                    "speed": float(eleven_config.get('Speed', 1.06))
                }
            }
        else:
            payload = {
                "text": chunk_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.7
                }
            }
        try:
            print(f"[DEBUG] ElevenLabs API payload: {json.dumps(payload)[:500]}{'...' if len(json.dumps(payload)) > 500 else ''}")
            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            elapsed = time.time() - start_time
            print(f"[DEBUG] ElevenLabs API call took {elapsed:.2f} seconds")
            print(f"[DEBUG] ElevenLabs REST API response status: {response.status_code}")
            print(f"[DEBUG] ElevenLabs REST API response headers: {dict(response.headers)}")
            if response.status_code == 200:
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Audio chunk received and saved: {temp_path}")
                return temp_path
            else:
                print(f"❌ ElevenLabs REST API error: {response.status_code} {response.text}")
                # Try to print error message from JSON if available
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        print(f"❌ ElevenLabs API error message: {error_json['error']}")
                    else:
                        print(f"❌ ElevenLabs API error JSON: {error_json}")
                except Exception:
                    print(f"❌ ElevenLabs API error (non-JSON): {response.content[:500]}")
                return None
        except requests.exceptions.Timeout:
            print("❌ ElevenLabs REST API error: Request timed out after 120 seconds.")
            traceback.print_exc()
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ ElevenLabs REST API error: {e}")
            traceback.print_exc()
            if hasattr(e, 'response') and e.response is not None:
                print(f"❌ ElevenLabs REST API error response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ ElevenLabs REST API error: {e}")
            traceback.print_exc()
            return None

    # Split text into <=2500 character chunks
    chunks = split_text_into_chunks(text, max_length=2500)
    if len(chunks) == 1:
        return _single_chunk(chunks[0], output_path)
    else:
        temp_audio_paths = []
        for idx, chunk_text in enumerate(chunks):
            temp_path = MP3_OUTPUT_DIR / f"temp_audio_{int(time.time())}_{os.getpid()}_chunk_{idx+1}.mp3"
            result = _single_chunk(chunk_text, temp_path)
            if result:
                temp_audio_paths.append(result)
            else:
                # Clean up any previous temp files
                for p in temp_audio_paths:
                    try: os.remove(p)
                    except: pass
                return None
        merged_path = MP3_OUTPUT_DIR / f"merged_audio_{int(time.time())}_{os.getpid()}.mp3"
        print(f"[DEBUG] Merging {len(temp_audio_paths)} chunk files into {merged_path}")
        merge_multiple_audio_files(temp_audio_paths, merged_path)
        for p in temp_audio_paths:
            try: os.remove(p)
            except: pass
        if merged_path and os.path.exists(merged_path):
            print(f"✅ Audio generated and merged successfully: {merged_path}")
        else:
            print(f"❌ Merged audio file {merged_path} was not created!")
        return merged_path

def download_latest_text_file_from_drive_oauth(folder_id):
    """Downloads the latest text file from a Google Drive folder using OAuth."""
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        drive_service = get_drive_service_oauth()
        
        # List files in the folder, sorted by modified time (newest first)
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType='text/plain'",
            orderBy='modifiedTime desc',
            pageSize=1,
            fields='files(id,name,modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        if not files:
            print(f"❌ No text files found in folder {folder_id}")
            return None
            
        latest_file = files[0]
        file_id = latest_file['id']
        file_name = latest_file['name']
        
        print(f"📥 Downloading latest text file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        content = fh.getvalue().decode('utf-8')
        print(f"✅ Downloaded {len(content)} characters from {file_name}")
        return content
        
    except Exception as e:
        print(f"❌ Error downloading file from Google Drive: {e}")
        return None

def upload_audio_to_drive_oauth(folder_id, filename, audio_file_path):
    """
    Uploads an audio file to a Google Drive folder using OAuth user credentials.
    Returns the file link.
    """
    try:
        service = get_drive_service_oauth()
        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'audio/mpeg'
        }
        media = MediaFileUpload(audio_file_path, mimetype='audio/mpeg')
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        return file.get('webViewLink')
    except Exception as e:
        print(f"❌ Error uploading audio to Google Drive: {e}")
        return None

def merge_audio(intro_path, main_path, outro_path, final_path):
    try:
        intro = AudioSegment.from_file(intro_path)
        main = AudioSegment.from_file(main_path)
        outro = AudioSegment.from_file(outro_path)
        final = intro + main + outro
        final.export(final_path, format="mp3")
        print(f"✅ Merged audio saved: {final_path}")
    except Exception as e:
        print(f"❌ Merge failed: {e}")

def download_latest_mp3_from_drive_oauth(folder_id):
    """Downloads the latest MP3 file from a Google Drive folder using OAuth."""
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        drive_service = get_drive_service_oauth()
        
        # List MP3 files in the folder, sorted by modified time (newest first)
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType='audio/mpeg'",
            orderBy='modifiedTime desc',
            pageSize=1,
            fields='files(id,name,modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        if not files:
            print(f"❌ No MP3 files found in folder {folder_id}")
            return None
            
        latest_file = files[0]
        file_id = latest_file['id']
        file_name = latest_file['name']
        
        print(f"📥 Downloading latest MP3 file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        # Save to temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_{file_name}"
        with open(temp_path, 'wb') as f:
            f.write(fh.getvalue())
        
        print(f"✅ Downloaded MP3 file: {temp_path}")
        return temp_path
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from Google Drive: {e}")
        return None

def download_mp3_file_from_drive_oauth(file_url):
    """Downloads a specific MP3 file from Google Drive using its URL with OAuth."""
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        # Extract file ID from Google Drive URL
        file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', file_url)
        if not file_id_match:
            print(f"❌ Invalid Google Drive file URL: {file_url}")
            return None
        
        file_id = file_id_match.group(1)
        
        drive_service = get_drive_service_oauth()
        
        # Get file metadata
        file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name', 'unknown_file.mp3')
        
        print(f"📥 Downloading MP3 file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        # Save to temporary file
        temp_path = MP3_OUTPUT_DIR / f"temp_{file_name}"
        with open(temp_path, 'wb') as f:
            f.write(fh.getvalue())
        
        print(f"✅ Downloaded MP3 file: {temp_path}")
        return temp_path
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from Google Drive: {e}")
        return None

def merge_multiple_audio_files(audio_paths, output_path):
    """Merges multiple audio files into a single MP3 file."""
    try:
        if not audio_paths:
            print("❌ No audio files provided for merging")
            return None
        
        print(f"🔗 Merging {len(audio_paths)} audio files...")
        
        # Load the first audio file
        combined = AudioSegment.from_file(audio_paths[0])
        print(f"  - Loaded: {audio_paths[0]}")
        
        # Add subsequent audio files
        for i, audio_path in enumerate(audio_paths[1:], 1):
            audio = AudioSegment.from_file(audio_path)
            combined += audio
            print(f"  - Added: {audio_path}")
        
        # Export the combined audio
        combined.export(output_path, format="mp3")
        print(f"✅ Merged audio saved: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"❌ Error merging audio files: {e}")
        return None

# -----------------------------------------
# MAIN EXECUTION
# -----------------------------------------
if __name__ == '__main__':
    print("🚀 Starting AI Workflow Pipeline")

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    print("✅ Workbook loaded. Starting workflow processing...")
    gc = connect_to_google_sheet_with_retry()
    spreadsheet = gc.open(GOOGLE_SHEET_NAME)
    workflow_ws = spreadsheet.worksheet("Workflows")
    outputs_ws = spreadsheet.worksheet("Outputs")
    requests_ws = spreadsheet.worksheet("Requests")
    prompts_ws = spreadsheet.worksheet("Prompts")
    models_ws = spreadsheet.worksheet("Models")
    workflow_steps_ws = spreadsheet.worksheet("Workflow Steps")
    locations_ws = spreadsheet.worksheet("Locations")

    # Try to load Eleven tab (may not exist in older sheets)
    eleven_ws = None
    try:
        eleven_ws = spreadsheet.worksheet("Eleven")
    except Exception:
        pass  # If the Eleven tab doesn't exist, skip it

    workflow_df = pd.DataFrame(workflow_ws.get_all_records())
    outputs_df = pd.DataFrame(outputs_ws.get_all_records())
    requests_df = pd.DataFrame(requests_ws.get_all_records())
    prompts_df = pd.DataFrame(prompts_ws.get_all_records())
    models_df = pd.DataFrame(models_ws.get_all_records())
    workflow_steps_df = pd.DataFrame(workflow_steps_ws.get_all_records())
    locations_df = pd.DataFrame(locations_ws.get_all_records()) if locations_ws is not None else pd.DataFrame(columns=["Location ID", "Location Description", "Type", "File Or Folder", "Location", "Latest"])
    eleven_df = pd.DataFrame(eleven_ws.get_all_records()) if eleven_ws is not None else pd.DataFrame(columns=["Eleven ID", "Voice", "Model", "Stability", "Similarity Boost", "Style", "Speed"])

    logs_ws = None
    try:
        logs_ws = spreadsheet.worksheet("Logs")
    except Exception:
        pass  # If the Logs tab doesn't exist, skip logging

    logs_df = pd.DataFrame(logs_ws.get_all_records()) if logs_ws else pd.DataFrame(columns=["Log ID", "Log Timestamp", "Log Message"])

    def get_next_log_id():
        if logs_df.empty or 'Log ID' not in logs_df.columns:
            return 1
        return int(logs_df['Log ID'].astype(int).max()) + 1

    def log_error(message):
        if logs_ws is not None:
            log_row = [get_next_log_id(), pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(message)]
            logs_ws.append_row(log_row)
        print(f"[LOGGED ERROR] {message}")

    # Helper to get next Output ID
    def get_next_output_id():
        if outputs_df.empty:
            return 1
        return outputs_df['Output ID'].astype(int).max() + 1

    # Helper to get next Workflow Steps ID
    def get_next_workflow_steps_id():
        if workflow_steps_df.empty:
            return 1
        return workflow_steps_df['Workflow Steps ID'].astype(int).max() + 1

    # Helper to get model name by Model ID
    def get_model_name(model_id):
        row = models_df[models_df['Model ID'].astype(str) == str(model_id)]
        if not row.empty:
            return row.iloc[0]['Model Name']
        return None

    # Helper to get Model ID by model name (returns the first match)
    def get_model_id_by_name(model_name):
        row = models_df[models_df['Model Name'] == model_name]
        if not row.empty:
            return str(row.iloc[0]['Model ID'])
        return None

    # Helper to get web search flag for a model by Model ID
    def get_model_web_search_by_id(model_id):
        row = models_df[models_df['Model ID'].astype(str) == str(model_id)]
        if not row.empty:
            return str(row.iloc[0].get('Web Search', 'N')).strip().upper() == 'Y'
        return False

    # Helper to get web search flag for a model by name (first match)
    def get_model_web_search_by_name(model_name):
        row = models_df[models_df['Model Name'] == model_name]
        if not row.empty:
            return str(row.iloc[0].get('Web Search', 'N')).strip().upper() == 'Y'
        return False

    # Helper to get prompt description by Prompt ID
    def get_prompt_desc(prompt_id):
        row = prompts_df[prompts_df['Prompt ID'].astype(str) == str(prompt_id)]
        if not row.empty:
            return row.iloc[0]['Prompt Description']
        return None

    # Helper to get default model for workflow
    def get_workflow_default_model(workflow_row):
        return workflow_row['Model Default'] if 'Model Default' in workflow_row else 'gpt-4o'

    # Helper to extract Google Drive folder ID from URL
    def extract_drive_folder_id(url):
        match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        return None

    # Helper to upload a text file to Google Drive folder and return the file link
    def upload_text_to_drive_oauth(folder_id, filename, text):
        """Uploads a text file to Google Drive folder using OAuth and returns the file link."""
        from googleapiclient.http import MediaInMemoryUpload
        
        try:
            drive_service = get_drive_service_oauth()
            file_metadata = {
                'name': filename,
                'parents': [folder_id],
                'mimeType': 'text/plain'
            }
            media = MediaInMemoryUpload(text.encode('utf-8'), mimetype='text/plain')
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
            return file.get('webViewLink')
        except Exception as e:
            print(f"❌ Error uploading text to Google Drive: {e}")
            return None

    # Helper to get Eleven Labs configuration by Eleven ID
    def get_eleven_config(eleven_id):
        row = eleven_df[eleven_df['Eleven ID'].astype(str) == str(eleven_id)]
        if not row.empty:
            return row.iloc[0].to_dict()
        return None

    # Helper to get voice ID by Eleven ID (this would need to be configured based on your Eleven Labs voice IDs)
    def get_voice_id_by_eleven_id(eleven_id):
        # This mapping should be updated with your actual Eleven Labs voice IDs
        voice_mapping = {
            "1": "TX3LPaxmHKxFdv7VOQHJ",  # Liam voice ID from Eleven Labs
            # Add more mappings as needed
        }
        return voice_mapping.get(str(eleven_id))

    # Helper to get location by Location ID
    def get_location_by_id(location_id):
        row = locations_df[locations_df['Location ID'].astype(str) == str(location_id)]
        if not row.empty:
            return row.iloc[0].to_dict()
        return None

    # Parse workflow code step (e.g. P2&R1M8)
    def parse_step(step, all_outputs, custom_topic):
        # Find model override (M#)
        model_override = None
        model_id_override = None
        m_match = re.search(r'M(\d+)', step)
        if m_match:
            model_id_override = m_match.group(1)
            model_override = get_model_name(model_id_override)
            step = re.sub(r'M\d+', '', step)
        # Split by & for combining
        parts = [p.strip() for p in step.split('&')]
        input_text = ''
        for i, part in enumerate(parts):
            print(f"Processing part: '{part}'")
            if part.startswith('P'):
                prompt_id = part[1:]
                prompt_text = get_prompt_desc(prompt_id)
                if i > 0:  # Add separator if not the first part
                    input_text += '\n\n'
                input_text += prompt_text or ''
                print(f"  [P{prompt_id}] First 100 chars: {str(prompt_text)[:100]}{'...' if prompt_text and len(prompt_text) > 100 else ''}")
            elif part.startswith('R'):
                match = re.match(r'R(\d+)', part)
                if match:
                    resp_idx = int(match.group(1)) - 1
                    if 0 <= resp_idx < len(all_outputs):
                        if i > 0:
                            input_text += '\n\n'
                        resp_text = all_outputs[resp_idx]
                        input_text += resp_text or ''
                        print(f"  [R{match.group(1)}] First 100 chars: {str(resp_text)[:100]}{'...' if resp_text and len(resp_text) > 100 else ''}")
            elif part == 'C':
                custom_text = custom_topic or ''
                if i > 0:
                    input_text += '\n\n'
                input_text += custom_text
                print(f"  [C] First 100 chars: {str(custom_text)[:100]}{'...' if custom_text and len(custom_text) > 100 else ''}")
        # Only print the first 100 characters of the final input
        print(f"    Input (first 100): {input_text[:100]}{'...' if len(input_text) > 100 else ''}")
        return input_text, model_override, model_id_override

    # Add to_native helper at top-level so it is available everywhere
    def to_native(val):
        if hasattr(val, 'item'):
            return val.item()
        if isinstance(val, (int, float, str)) or val is None:
            return val
        return str(val)

    # Helper to convert column number to Excel column letters
    def colnum_to_excel_col(n):
        """Convert a 1-based column index to Excel column letters."""
        result = ''
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result
        return result

    # Main workflow loop
    for req_idx, req_row in requests_df.iterrows():
        if str(req_row.get('Active', '')).strip().upper() != 'Y':
            continue
        request_id = req_row['Request ID']
        workflow_id = req_row['Workflow ID']
        custom_topic = req_row.get('Custom Topic If Required', '')
        print(f"\n🔔 Processing Request ID {request_id} for Workflow ID {workflow_id}")
        workflow_row = workflow_df[workflow_df['Workflow ID'] == workflow_id]
        if workflow_row.empty:
            print(f"  - ⚠ Workflow ID {workflow_id} not found.")
            continue
        workflow_row = workflow_row.iloc[0]
        workflow_code = workflow_row['Workflow Code']
        default_model = get_workflow_default_model(workflow_row)
        default_model_id = get_model_id_by_name(default_model)
        steps = [s.strip() for s in workflow_code.split(',') if s.strip()]
        print(f"[DEBUG] Steps to execute: {steps}")
        all_outputs = []  # Track output for every step, even if None
        workflow_steps_records = []
        current_output_id = outputs_df['Output ID'].astype(int).max() if not outputs_df.empty else 0
        output_record = {
            'Output ID': current_output_id + 1,
            'Triggered Date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        # Ensure all Output columns are present in output_record
        for col in outputs_df.columns:
            if col not in output_record:
                output_record[col] = ''
        # Create the initial row in the Outputs tab
        output_row = [to_native(output_record.get(col, '')) for col in outputs_df.columns]
        outputs_ws.append_row(output_row)
        # Get the row number of the newly created row
        current_output_row = len(outputs_df) + 2  # +2 because of 1-based indexing and header row
        print(f"[INFO] Created Output ID: {output_record['Output ID']} at row {current_output_row}")
        executed_steps = set()
        for i, step in enumerate(steps):
            print(f"[DEBUG] Executing step {i+1}/{len(steps)}: {step}")
            executed_steps.add(i)
            try:
                # 1. PPU step FIRST
                if step == 'PPU':
                    print(f"  - Step {i+1}: {step} (Posted Podcasts Update Step)")
                    RSS_FEED_URL = 'https://anchor.fm/s/101530384/podcast/rss'
                    try:
                        response = requests.get(RSS_FEED_URL)
                        response.raise_for_status()
                        root = ET.fromstring(response.content)
                        channel = root.find('channel')
                        items = channel.findall('item') if channel is not None else []
                        posted_podcasts_data = []
                        # Reverse items so oldest is first, newest is last
                        items = items[::-1]
                        for idx, item in enumerate(items):
                            title = item.findtext('title', default='')
                            description = item.findtext('description', default='')
                            # Decode HTML entities
                            title = html.unescape(title)
                            description = html.unescape(description)
                            # Remove HTML tags from description
                            import re
                            cleanr = re.compile('<.*?>')
                            description_clean = re.sub(cleanr, '', description)
                            # Description Short: up to 'Help support' (case-insensitive)
                            desc_short = description_clean.split('Help support')[0].strip()
                            posted_podcasts_data.append([
                                idx + 1,  # Sequential ID starting from 1
                                title,
                                description_clean,
                                desc_short
                            ])
                        # Update the Posted Podcasts tab
                        try:
                            posted_ws = spreadsheet.worksheet('Posted Podcasts')
                            num_rows = len(posted_podcasts_data) + 1  # +1 for header
                            num_cols = max(len(row) for row in posted_podcasts_data) if posted_podcasts_data else 4
                            posted_ws.resize(rows=num_rows, cols=num_cols)
                            posted_ws.update(values=posted_podcasts_data, range_name='A2')
                            log_msg = f"Updated Posted Podcasts tab with {len(posted_podcasts_data)} episodes."
                            print(f"    > {log_msg}")
                        except Exception as e:
                            log_msg = f"Failed to update Posted Podcasts tab: {e}"
                            print(f"    > {log_msg}")
                    except Exception as e:
                        log_msg = f"Failed to fetch or parse RSS feed: {e}"
                        print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    all_outputs.append(None)
                    continue

                # 2. PPL# step SECOND
                ppl_match = re.fullmatch(r'PPL(\d+)', step)
                if ppl_match:
                    num_episodes = int(ppl_match.group(1))
                    print(f"  - Step {i+1}: {step} (Posted Podcast Last Step, retrieving last {num_episodes} episodes)")
                    try:
                        posted_ws = spreadsheet.worksheet('Posted Podcasts')
                        posted_df = pd.DataFrame(posted_ws.get_all_records())
                        # Sort by Posted Podcasts ID descending (numeric)
                        if 'Posted Podcasts ID' in posted_df.columns:
                            try:
                                posted_df['Posted Podcasts ID'] = posted_df['Posted Podcasts ID'].astype(int)
                                posted_df_sorted = posted_df.sort_values(by='Posted Podcasts ID', ascending=False)
                            except Exception:
                                posted_df_sorted = posted_df.iloc[::-1]
                        else:
                            posted_df_sorted = posted_df.iloc[::-1]
                        # Get the last N episodes
                        last_episodes = posted_df_sorted.head(num_episodes)
                        # Prepare output: Title and Description Short for each
                        output_lines = []
                        for idx, row in last_episodes.iterrows():
                            title = row.get('Title', '')
                            desc_short = row.get('Description Short', '')
                            output_lines.append(f"Title: {title}\nDescription Short: {desc_short}")
                        ppl_output = '\n\n'.join(output_lines)
                        output_col_in = f'Output {2*i+1}'
                        output_col_out = f'Output {2*i+2}'
                        output_record[output_col_in] = f"PPL{num_episodes}"
                        output_record[output_col_out] = ppl_output
                        log_msg = f"Retrieved last {num_episodes} posted podcast episodes."
                        print(f"    > {log_msg}")
                    except Exception as e:
                        ppl_output = ''
                        log_msg = f"Failed to retrieve posted podcasts: {e}"
                        print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        f"PPL{num_episodes}",
                        ppl_output,
                        log_msg
                    ])
                    # After each step, update the Outputs tab with the current output_record
                    output_row = [to_native(output_record.get(col, '')) for col in outputs_df.columns]
                    last_col_letter = colnum_to_excel_col(len(outputs_df.columns))
                    outputs_ws.update(f'A{current_output_row}:{last_col_letter}{current_output_row}', [output_row])
                    # Only print the first 100 characters of the output
                    output_col_out = f'Output {2*i+2}'
                    output_val = output_record.get(output_col_out, '')
                    print(f"    Output (first 100): {str(output_val)[:100]}{'...' if output_val and len(str(output_val)) > 100 else ''}")
                    print(f"[INFO] Output updated for Output ID: {output_record['Output ID']} after step {i+1}")
                    all_outputs.append(ppl_output)
                    continue

                # Check for save-only step (e.g., R4SL7)
                save_only_match = re.fullmatch(r'R(\d+)SL(\d+)', step)
                if save_only_match:
                    print(f"  - Step {i+1}: {step} (Save-Only Step)")
                    resp_idx = int(save_only_match.group(1)) - 1
                    location_id = save_only_match.group(2)
                    response_to_save = None
                    log_msg = ''
                    if 0 <= resp_idx < len(all_outputs):
                        response_to_save = all_outputs[resp_idx]
                        # Always fix encoding before saving
                        response_to_save = fix_text_encoding(response_to_save)
                        response_to_save = force_clean_mojibake(response_to_save)
                        loc_row = locations_df[locations_df['Location ID'].astype(str) == location_id]
                        if not loc_row.empty:
                            folder_url = loc_row.iloc[0]['Location']
                            # For GCS: Use the folder prefix directly
                            folder_prefix = folder_url.rstrip('/')  # Clean up any trailing slash
                            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                            filename = f'workflow_{request_id}_step_{i+1}_{timestamp}.txt'
                            try:
                                file_link = upload_text_to_gcs(response_to_save, f"{folder_prefix}/{filename}")
                                log_msg = f"Saved response to Google Cloud Storage: {file_link}"
                            except Exception as e:
                                log_msg = f"Failed to save response to Google Cloud Storage: {e}"
                        else:
                            log_msg = f"Location ID {location_id} not found in Locations sheet."
                    else:
                        log_msg = f"Response index {resp_idx+1} not found in previous outputs."
                    
                    print(f"    > {log_msg}")

                    # Always append a workflow step record for save-only steps
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,  # fractional ID to keep order
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        response_to_save if response_to_save is not None else '',
                        '',  # No new output
                        log_msg
                    ])
                    # Only append to prev_outputs if response_to_save is defined
                    if response_to_save is not None:
                        all_outputs.append(response_to_save)
                    else:
                        all_outputs.append(None)
                    continue  # Skip model call for this step
                
                # Check for Eleven Labs step (e.g., L8E1SL4)
                eleven_match = re.fullmatch(r'L(\d+)E(\d+)SL(\d+)', step)
                if eleven_match:
                    print(f"  - Step {i+1}: {step} (Eleven Labs Step)")
                    location_id = eleven_match.group(1)
                    eleven_id = eleven_match.group(2)
                    save_location_id = eleven_match.group(3)
                    
                    # Get location details for source folder
                    source_location = get_location_by_id(location_id)
                    if not source_location:
                        log_msg = f"Source location ID {location_id} not found in Locations sheet."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Get Eleven Labs configuration
                    eleven_config = get_eleven_config(eleven_id)
                    if not eleven_config:
                        log_msg = f"Eleven Labs configuration ID {eleven_id} not found in Eleven sheet."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Get voice ID
                    voice_id = get_voice_id_by_eleven_id(eleven_id)
                    if not voice_id:
                        log_msg = f"Voice ID not found for Eleven ID {eleven_id}. Please update voice_mapping in get_voice_id_by_eleven_id function."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Download latest text file from source location
                    source_folder_prefix = source_location['Location']  # Use GCS folder prefix directly
                    text_content = download_latest_text_file_from_gcs(source_folder_prefix)
                    if not text_content:
                        log_msg = f"Failed to download text file from source location {location_id}."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Generate audio using Eleven Labs
                    print(f"    > Generating audio with voice: {eleven_config['Voice']}")
                    temp_audio_path = MP3_OUTPUT_DIR / f"temp_audio_{request_id}_step_{i+1}.mp3"
                    audio_path = generate_voice_audio(text_content, voice_id, temp_audio_path, eleven_config)
                    
                    if not audio_path:
                        log_msg = f"Failed to generate audio with Eleven Labs for step {i+1}. Aborting workflow."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            text_content,
                            '',
                            log_msg
                        ])
                        # End the entire workflow immediately
                        print("[FATAL] Eleven Labs API error encountered. Exiting workflow.")
                        sys.exit(1)
                    
                    # Upload audio to destination location
                    save_location = get_location_by_id(save_location_id)
                    if not save_location:
                        log_msg = f"Save location ID {save_location_id} not found in Locations sheet."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            text_content,
                            audio_path,
                            log_msg
                        ])
                        continue
                    
                    save_folder_prefix = save_location['Location']  # Use GCS folder prefix directly
                    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                    audio_filename = f'workflow_{request_id}_step_{i+1}_{eleven_config["Voice"]}_{timestamp}.mp3'
                    try:
                        print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                        start_time = time.time()
                        if os.path.exists(audio_path):
                            # Clean up the path to avoid double slashes
                            clean_prefix = save_folder_prefix.rstrip('/')
                            destination_path = f"{clean_prefix}/{audio_filename}"
                            file_link = upload_audio_to_gcs(audio_path, destination_path)
                            log_msg = f"Generated and uploaded audio to Google Cloud Storage: {file_link}"
                            print(f"    > {log_msg}")
                        else:
                            print(f"File {audio_path} does not exist, skipping upload.")
                            sys.exit(1)
                    except Exception as e:
                        log_msg = f"Failed to upload audio to Google Cloud Storage: {e}"
                        print(f"    > {log_msg}")
                        sys.exit(1)
                    
                    # Clean up temporary file
                    try:
                        os.remove(temp_audio_path)
                    except:
                        pass
                    
                    # Add workflow step record
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        text_content,
                        audio_path,
                        log_msg
                    ])
                    
                    # Add audio path to outputs
                    all_outputs.append(audio_path)
                    continue  # Skip regular model call for this step
                
                # Check for Audio Merging step (e.g., L1&L9&L2SL3)
                audio_merge_match = re.fullmatch(r'L(\d+)(?:&L(\d+))*SL(\d+)', step)
                if audio_merge_match:
                    print(f"  - Step {i+1}: {step} (Audio Merging Step)")
                    
                    # Extract all location IDs from the step
                    location_ids = re.findall(r'L(\d+)', step)
                    save_location_id = location_ids[-1]  # Last location ID is the save location
                    source_location_ids = location_ids[:-1]  # All others are source locations
                    
                    if len(source_location_ids) < 2:
                        log_msg = f"Audio merging requires at least 2 source locations, found {len(source_location_ids)}"
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Download audio files from source locations
                    audio_paths = []
                    download_errors = []
                    
                    for loc_id in source_location_ids:
                        location = get_location_by_id(loc_id)
                        if not location:
                            error_msg = f"Location ID {loc_id} not found in Locations sheet."
                            download_errors.append(error_msg)
                            continue
                        
                        location_url = location['Location']
                        location_type = location['Type']
                        
                        if location_type == 'File':
                            # Download specific file
                            audio_path = download_mp3_file_from_gcs(location_url)
                        elif location_type == 'mp3':
                            # For GCS: Use the folder prefix directly to get the latest mp3
                            folder_prefix = location_url  # Already set to e.g. 'eleven-labs/'
                            audio_path = download_latest_mp3_from_gcs(folder_prefix)
                            if not audio_path:
                                error_msg = f"Failed to download latest mp3 from folder {folder_prefix} for location {loc_id}"
                                download_errors.append(error_msg)
                                continue
                        else:
                            error_msg = f"Location {loc_id} is not a file or mp3 type"
                            download_errors.append(error_msg)
                            continue
                        
                        if audio_path:
                            audio_paths.append(audio_path)
                        else:
                            error_msg = f"Failed to download audio from location {loc_id}"
                            download_errors.append(error_msg)
                    
                    if download_errors:
                        log_msg = f"Audio download errors: {'; '.join(download_errors)}"
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    if len(audio_paths) < 2:
                        log_msg = f"Not enough audio files downloaded for merging. Expected at least 2, got {len(audio_paths)}"
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            '',
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Merge audio files
                    print(f"    > Merging {len(audio_paths)} audio files...")
                    merged_audio_path = MP3_OUTPUT_DIR / f"merged_audio_{request_id}_step_{i+1}.mp3"
                    merged_path = merge_multiple_audio_files(audio_paths, merged_audio_path)
                    
                    if not merged_path:
                        log_msg = f"Failed to merge audio files for step {i+1}"
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            str(audio_paths),
                            '',
                            log_msg
                        ])
                        continue
                    
                    # Upload merged audio to destination location
                    save_location = get_location_by_id(save_location_id)
                    if not save_location:
                        log_msg = f"Save location ID {save_location_id} not found in Locations sheet."
                        print(f"    > {log_msg}")
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            str(audio_paths),
                            merged_path,
                            log_msg
                        ])
                        continue
                    
                    save_folder_prefix = save_location['Location']  # Use GCS folder prefix directly
                    timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                    audio_filename = f'merged_workflow_{request_id}_step_{i+1}_{timestamp}.mp3'
                    
                    try:
                        start_time = time.time()
                        if os.path.exists(merged_path):
                            # Clean up the path to avoid double slashes
                            clean_prefix = save_folder_prefix.rstrip('/')
                            destination_path = f"{clean_prefix}/{audio_filename}"
                            file_link = upload_audio_to_gcs(merged_path, destination_path)
                            log_msg = f"Merged and uploaded audio to Google Cloud Storage: {file_link}"
                            print(f"    > {log_msg}")
                        else:
                            print(f"File {merged_path} does not exist, skipping upload.")
                    except Exception as e:
                        log_msg = f"Failed to upload merged audio to Google Cloud Storage: {e}"
                        print(f"    > {log_msg}")
                    # Clean up temporary files
                    for temp_path in audio_paths:
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    # Add workflow step record
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        str(audio_paths),
                        merged_path,
                        log_msg
                    ])
                    # Add merged audio path to outputs
                    all_outputs.append(merged_path)
                    continue  # Skip regular model call for this step
                
                # Parse the step for prompt, model override, and model ID override
                input_text, model_override, model_id_override = parse_step(step, all_outputs, custom_topic)
                # print(f"    Input (first 100): {input_text[:100]}{'...' if len(input_text) > 100 else ''}")  # Removed duplicate debug print
                if model_override and model_id_override:
                    model_to_use = model_override
                    web_search_enabled = get_model_web_search_by_id(model_id_override)
                else:
                    model_to_use = default_model
                    web_search_enabled = get_model_web_search_by_id(default_model_id)
                print(f"  - Step {i+1}: {step} (Model: {model_to_use}, Web Search: {web_search_enabled})")
                # Fallback for OpenAI client if responses.create is not available
                if web_search_enabled and not hasattr(client, 'responses'):
                    msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                    log_error(msg)
                    response = "[Web search not supported by your OpenAI Python package version]"
                else:
                    response = call_openai_model(input_text, model_to_use, web_search=web_search_enabled)
                
                # Ensure response is properly encoded as UTF-8
                if isinstance(response, bytes):
                    response = response.decode('utf-8')
                elif not isinstance(response, str):
                    response = str(response)
                
                output_col_in = f'Output {2*i+1}'
                output_col_out = f'Output {2*i+2}'
                output_record[output_col_in] = input_text
                output_record[output_col_out] = response
                # Check for SL# pattern in step (e.g., R4SL7)
                sl_match = re.search(r'SL(\d+)', step)
                if sl_match:
                    location_id = sl_match.group(1)
                    loc_row = locations_df[locations_df['Location ID'].astype(str) == location_id]
                    if not loc_row.empty:
                        folder_url = loc_row.iloc[0]['Location']
                        # For GCS: Use the folder prefix directly
                        folder_prefix = folder_url.rstrip('/')  # Clean up any trailing slash
                        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
                        filename = f'workflow_{request_id}_step_{i+1}_{timestamp}.txt'
                        try:
                            file_link = upload_text_to_gcs(response, f"{folder_prefix}/{filename}")
                            log_msg = f"Saved response to Google Cloud Storage: {file_link}"
                        except Exception as e:
                            log_msg = f"Failed to save response to Google Cloud Storage: {e}"
                        # Add file link or error to Workflow Steps log message
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,  # fractional ID to keep order
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            input_text,
                            response,
                            log_msg
                        ])
                # After each step, update the Outputs tab with the current output_record
                output_row = [to_native(output_record.get(col, '')) for col in outputs_df.columns]
                last_col_letter = colnum_to_excel_col(len(outputs_df.columns))
                outputs_ws.update(f'A{current_output_row}:{last_col_letter}{current_output_row}', [output_row])
                # Only print the first 100 characters of the output
                output_col_out = f'Output {2*i+2}'
                output_val = output_record.get(output_col_out, '')
                print(f"    Output (first 100): {str(output_val)[:100]}{'...' if output_val and len(str(output_val)) > 100 else ''}")
                print(f"[INFO] Output updated for Output ID: {output_record['Output ID']} after step {i+1}")
                all_outputs.append(response)
            except Exception as e:
                error_msg = f"[ERROR] Exception in step {i+1} ({step}): {e}"
                print(error_msg)
                log_error(error_msg)
                all_outputs.append(None)
                print("[FATAL] Workflow execution halted due to error.")
                sys.exit(1)

        # Write to Workflow Steps tab
        for ws_row in workflow_steps_records:
            ws_row_native = [to_native(x) for x in ws_row]
            workflow_steps_ws.append_row(ws_row_native)
        # Mark request as processed (disabled per user request)
        # requests_ws.update_cell(req_idx + 2, requests_df.columns.get_loc('Active') + 1, 'N')
        print(f"✅ Request {request_id} processed and logged.")

    # After the loop, check if all steps were executed
    if len(executed_steps) != len(steps):
        print(f"[WARNING] Not all workflow steps were executed! Steps: {len(steps)}, Executed: {len(executed_steps)}")
    else:
        print(f"[DEBUG] All workflow steps executed: {len(steps)} steps.")

    # print("Critical error message")
    # sys.exit(1)

import os
from dotenv import load_dotenv

load_dotenv()
github_pat = os.getenv("GH_PAT")

# -----------------------------------------
# GOOGLE DRIVE OAUTH AUTHENTICATION
# -----------------------------------------