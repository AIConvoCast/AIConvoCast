import os
import pandas as pd
import gspread
import requests
import openai
from openai import OpenAI
from pydub import AudioSegment
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'jmio-google-api.json'
GOOGLE_SHEET_NAME = 'AI Podcast Workflow'
GOOGLE_DRIVE_FOLDER_ID = '17XAnga8MC1o23rFhiQ7fcrrqDNhz_-oB'  # Folder to create the sheet in
SHARE_SHEET_WITH_EMAIL = 'ianeoconnell@gmail.com' # <--- CHANGE THIS TO YOUR EMAIL

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-key')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', 'your-elevenlabs-key')

# Instantiate the OpenAI client once using the API key from environment variables
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------------------
# GOOGLE SHEET SUPPORT
# -----------------------------------------
def create_and_setup_google_sheet(gc, sheet_name, folder_id, user_email):
    """Creates and populates a new Google Sheet with the required structure."""
    print(f"✨ Creating new Google Sheet '{sheet_name}'...")
    spreadsheet = gc.create(sheet_name, folder_id=folder_id)
    spreadsheet.share(user_email, perm_type='user', role='writer')

    template_dfs = get_template_dataframes()
    sheet_order = ["Episode Tracker", "Instructions", "Prompts", "Manual Episode Ideas", "Prompts Used", "Settings"]

    # Rename the initial "Sheet1" and populate it
    ws = spreadsheet.worksheet("Sheet1")
    ws.update_title(sheet_order[0])
    df = template_dfs.get(sheet_order[0])
    if df is not None:
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"  - Created and formatted sheet: {sheet_order[0]}")

    # Add and populate the remaining sheets in the correct order
    for title in sheet_order[1:]:
        df = template_dfs.get(title)
        if df is not None:
            ws = spreadsheet.add_worksheet(title=title, rows=100, cols=20)
            ws.update([df.columns.values.tolist()] + df.values.tolist())
            if title in ["Instructions", "Prompts"]:
                ws.format('C:C', {'wrapStrategy': 'WRAP'}) # Make long text readable
            print(f"  - Created and formatted sheet: {title}")

    print(f"✅ Google Sheet created and shared with {user_email}.")
    return spreadsheet


def connect_to_google_sheet():
    """Connects to Google Sheets using service account credentials."""
    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    return gspread.service_account(filename=GOOGLE_CREDS_JSON, scopes=scopes)

def try_load_google_sheet():
    try:
        gc = connect_to_google_sheet()
        try:
            spreadsheet = gc.open(GOOGLE_SHEET_NAME)

            # --- Retrofit existing sheets with new structure ---
            existing_worksheets = [ws.title for ws in spreadsheet.worksheets()]
            template_dfs = get_template_dataframes()

            # Add Instructions sheet if missing
            if "Instructions" not in existing_worksheets:
                print("📝 Adding 'Instructions' sheet to existing workbook...")
                df = template_dfs.get("Instructions")
                ws = spreadsheet.add_worksheet(title="Instructions", rows=20, cols=5, index=1)
                ws.update([df.columns.values.tolist()] + df.values.tolist())
                ws.format('C:C', {'wrapStrategy': 'WRAP'})
                print("  - 'Instructions' sheet added.")

            # Add Prompts sheet if missing
            if "Prompts" not in existing_worksheets:
                print("📝 Adding 'Prompts' sheet to existing workbook...")
                df = template_dfs.get("Prompts")
                ws = spreadsheet.add_worksheet(title="Prompts", rows=20, cols=5, index=2)
                ws.update([df.columns.values.tolist()] + df.values.tolist())
                ws.format('C:C', {'wrapStrategy': 'WRAP'})
                print("  - 'Prompts' sheet added.")

            # Add 'Prompt ID' column to 'Episode Tracker' if it's missing
            ep_tracker_ws = spreadsheet.worksheet("Episode Tracker")
            headers = ep_tracker_ws.row_values(1)
            if "Prompt ID" not in headers:
                print("📝 Adding 'Prompt ID' column to 'Episode Tracker' sheet...")
                col_index = len(headers) + 1
                ep_tracker_ws.update_cell(1, col_index, "Prompt ID")
                print("  - 'Prompt ID' column added.")
            # --- End retrofit ---

        except gspread.exceptions.SpreadsheetNotFound:
            spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)

        return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in spreadsheet.worksheets()}
    except Exception as e:
        print(f"⚠ Google Sheets not accessible: {e}")
        return None

# -----------------------------------------
# EXCEL FALLBACK STRUCTURE
# -----------------------------------------
def get_template_dataframes():
    """Returns a dictionary of DataFrames for the template structure."""
    episode_tracker = pd.DataFrame(columns=[
        "Episode ID", "Episode Date", "Type", "Topic Title", "Prompt ID", "Manual Prompt",
        "Model: Story Selection", "Model: Research", "Model: Script Gen", "Model: Title Desc",
        "Intro File Name", "Outro File Name",
        "Story 1 Title", "Story 2 Title", "Story 3 Title",
        "Research 1", "Research 2", "Research 3",
        "Script", "Episode Title", "Episode Description",
        "Audio File URL", "Status", "Error Log"
    ])
    manual_ideas = pd.DataFrame(columns=[
        "ID", "Episode Title (Idea)", "Topic Prompt",
        "Model: Research", "Model: Script",
        "Intro File Name", "Outro File Name",
        "Expanded Research", "Script Generated?", "Final Script", "Episode Ready?"
    ])
    prompts_used = pd.DataFrame(columns=[
        "Prompt Step", "Model Used", "Prompt Text", "Tokens Used", "Cost (USD)", "Timestamp"
    ])
    instructions_data = [
        [
            "Workflow", "1. Use the 'Prompts' Tab", "Create and manage your reusable prompts in the 'Prompts' tab. Each prompt needs a unique 'Prompt ID'."
        ],
        [
            "", "2. Plan in 'Episode Tracker'", "Add a new episode row. To use a standard prompt, enter its 'Prompt ID' in the 'Prompt ID' column."
        ],
        [
            "", "3. For One-Off Tasks", "If you have a unique, one-time task, leave 'Prompt ID' blank and write the full prompt in the 'Manual Prompt' column."
        ],
        [
            "", "4. Run the Script", "Execute the Python script. It will find the right prompt, generate the content, and produce the audio."
        ]
    ]
    instructions = pd.DataFrame(instructions_data, columns=["Category", "Step", "Description"])

    prompts_data = [
        [
            1, "Daily News",
            ("Please provide a comprehensive overview of the most important news in AI that occurred in the last 24-48 hours "
             "and mention dates of when the news items or recent updates occurred to confirm occurrence in the last 24-48 hours. "
             "AI news can be in relation to AI model releases, Expected tool releases, New enhancements released for AI tools or other "
             "interesting topics related to AI technology, AI company announcements, models, tool releases, enhancements, etc. "
             "Please be sure to summarize as many sources as possible and also provide numerous quotes from both company representatives, "
             "reporters as well as user feedback on social media.")
        ],
        [
            2, "Generate All On Appended Topic",
            ("Generate all details related to the news stories below from the last 24-48 hours. Please make sure to include "
             "any and all quotes from participants, companies or even social media reactions that have received significant "
             "engagement. Please also include technical specifications if required. Please ensure complete coverage provided  "
             "details to ensure comprehensive coverage of story. Stories to retrieve all relevant details on: ")
        ]
    ]
    prompts = pd.DataFrame(prompts_data, columns=["Prompt ID", "Prompt Title", "Prompt Description"])

    settings_data = [
        ["default_model_story_select", "gpt-4o"],
        ["default_model_research", "gpt-4o"],
        ["default_model_script", "gpt-4o"],
        ["default_model_title_desc", "claude-3-haiku"],
        ["base_audio_folder_path", "C:/podcast/audio_assets/"],
        ["default_intro_file", "intro_default.mp3"],
        ["default_outro_file", "outro_default.mp3"],
        ["upload_folder_id", "drive-folder-xyz123"],
        ["daily_trigger_time", "07:00 EST"],
        ["elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"]
    ]
    settings = pd.DataFrame(settings_data, columns=["Setting Key", "Value"])

    return {
        "Episode Tracker": episode_tracker,
        "Manual Episode Ideas": manual_ideas,
        "Instructions": instructions,
        "Prompts": prompts,
        "Prompts Used": prompts_used,
        "Settings": settings
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
    # Google Sheets is now the primary, with automated creation
    data = try_load_google_sheet()
    if data:
        return data

    print("Falling back to local Excel file.")
    if os.path.exists(EXCEL_FILENAME):
        return pd.read_excel(EXCEL_FILENAME, sheet_name=None)
    if os.path.exists(EXCEL_BACKUP):
        return pd.read_excel(EXCEL_BACKUP, sheet_name=None)

    # Generate Excel only if Google Sheets fails and no local file exists
    generate_excel_template(EXCEL_FILENAME)
    return pd.read_excel(EXCEL_FILENAME, sheet_name=None)

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

# -----------------------------------------
# API CALLS
# -----------------------------------------
def call_openai_model(prompt, model="gpt-4o", temperature=0.7):
    """Calls the OpenAI Chat Completion API with the new v1.x syntax."""
    if not client.api_key:
        print("❌ OpenAI API key is not configured. Please check your .env file.")
        return ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except openai.APIConnectionError as e:
        print(f"❌ OpenAI API Connection Error: {e.__cause__}")
        return ""
    except openai.RateLimitError as e:
        print(f"❌ OpenAI Rate Limit Exceeded: {e.status_code} {e.response}")
        return ""
    except openai.APIStatusError as e:
        print(f"❌ OpenAI API Status Error: {e.status_code} {e.response}")
        return ""
    except Exception as e:
        print(f"❌ An unexpected OpenAI error occurred: {e}")
        return ""

def generate_voice_audio(text, voice_id, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.7
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return output_path
        else:
            print(f"❌ ElevenLabs error: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ ElevenLabs API error: {e}")
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

# -----------------------------------------
# MAIN EXECUTION
# -----------------------------------------
if __name__ == '__main__':
    print("🚀 Starting AI Podcast Pipeline")

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    print("✅ Workbook loaded. Starting episode processing...")
    episode_tracker = dfs.get("Episode Tracker")
    settings = dfs.get("Settings")
    prompts_df = dfs.get("Prompts")
    if prompts_df is not None:
        prompts_df['Prompt ID'] = prompts_df['Prompt ID'].astype(str) # For reliable matching

    for _, row in episode_tracker.iterrows():
        episode_id = row.get("Episode ID", "unknown")
        prompt_id = str(row.get("Prompt ID", "")).strip()

        print(f"🎙️ Processing Episode: {episode_id}")

        prompt = ""
        # Priority 1: Use Prompt ID
        if prompt_id and prompts_df is not None:
            # Find the prompt in the Prompts DataFrame
            prompt_row = prompts_df[prompts_df['Prompt ID'] == prompt_id]
            if not prompt_row.empty:
                prompt = prompt_row.iloc[0]['Prompt Description']
                prompt_title = prompt_row.iloc[0]['Prompt Title']
                print(f"  - Found prompt by ID '{prompt_id}': '{prompt_title}'")
            else:
                print(f"  - ⚠ Warning: Prompt ID '{prompt_id}' not found in 'Prompts' tab. Skipping.")
                continue
        # Priority 2: Fallback to Manual Prompt
        elif row.get("Manual Prompt") and str(row.get("Manual Prompt")).strip():
            prompt = row.get("Manual Prompt")
            print("  - Using 'Manual Prompt' from sheet.")
        # Otherwise, no prompt is available
        else:
            print("  - ⚠ Skipping episode: No 'Prompt ID' or 'Manual Prompt' provided.")
            continue

        model = get_model_for_step(row, "Research", settings)
        script = call_openai_model(prompt, model)

        if not script:
            print("  - ⚠ Skipping episode due to script generation failure.")
            continue

        voice_id = settings.loc[settings['Setting Key'] == 'elevenlabs_voice_id', 'Value'].values[0]
        tts_output = f"{episode_id}_main.mp3"
        final_output = f"{episode_id}_final.mp3"

        if generate_voice_audio(script, voice_id, tts_output):
            intro_path, outro_path = get_intro_outro_paths(row, settings)
            merge_audio(intro_path, tts_output, outro_path, final_output)

        print("✅ Episode complete")
        print("---")
