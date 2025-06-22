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

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'jmio-google-api.json'
GOOGLE_SHEET_NAME = 'AI Workflow'
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
    sheet_order = ["Workflows", "Outputs", "Requests", "Prompts", "Models", "Workflow Steps"]

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
        [2, "Test Daily News", "P1", "gpt-4o"]
    ], columns=["Workflow ID", "Workflow Title", "Workflow Code", "Model Default"])

    outputs = pd.DataFrame(columns=[
        "Output ID", "Triggered Date", "Output 1", "Output 2", "Output 3", "Output 4", "Output 5", "Output 6", "Output 7", "Output 8", "Output 9", "Output 10"
    ])

    requests = pd.DataFrame([
        [1, 1, "", "N"],
        [2, 2, "", "Y"]
    ], columns=["Request ID", "Workflow ID", "Custom Topic If Required", "Active"])

    prompts = pd.DataFrame([
        [1, "Daily News", "Please provide a comprehensive overview of the most important news in AI that occurred in the last 24-48 hours and mention dates of when the news items or recent updates occurred to confirm occurrence in the last 24-48 hours. AI news can be in relation to AI model releases, Expected tool releases, New enhancements released for AI tools or other interesting topics related to AI technology, AI company announcements, models, tool releases, enhancements, etc. Please be sure to summarize as many sources as possible and also provide numerous quotes from both company representatives, reporters as well as user feedback on social media."],
        [2, "Top 3 Topics", "Please select the top 3 news stories to generate podcast episodes on based on the top AI news stories below:"],
        [3, "Generate All On Appendend Topic", "Generate all details related to the news stories below from the last 24-48 hours. Please make sure to include any and all quotes from participants, companies or even social media reactions that have received significant engagement. Please also include technical specifications if required. Please ensure complete coverage provided details to ensure comprehensive coverage of story. Stories to retrieve all relevant details on:"]
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

    return {
        "Workflows": workflow,
        "Outputs": outputs,
        "Requests": requests,
        "Prompts": prompts,
        "Models": models,
        "Workflow Steps": workflow_steps
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

# -----------------------------------------
# API CALLS
# -----------------------------------------
def call_openai_model(prompt, model="gpt-4o", temperature=0.7, web_search=False):
    """Calls the OpenAI API, using the correct endpoint for web search and model type. Logs all errors and unexpected responses."""
    if not client.api_key:
        msg = "❌ OpenAI API key is not configured. Please check your .env file."
        log_error(msg)
        return ""
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
                return ""
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content.strip()
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            return ""
        # Case 2: Responses API with web_search_preview tool (base models)
        elif web_search:
            if not hasattr(client, 'responses'):
                msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                log_error(msg)
                return "[Web search not supported by your OpenAI Python package version]"
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
                return ""
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
                                    return text.strip()
                log_error(f"OpenAI Responses: Unexpected empty or malformed response. Full response: {response}")
                return ""
            except Exception as e:
                log_error(f"Error parsing OpenAI web search response: {e}\nRaw response: {response}")
                return ""
        # Case 3: Standard Chat Completions
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            # Robust error logging for chat completions
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI ChatCompletions error: {response.error}\nFull response: {response}")
                return ""
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content.strip()
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            return ""
    except Exception as e:
        log_error(f"OpenAI error: {e}")
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
    print("🚀 Starting AI Workflow Pipeline")

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    print("✅ Workbook loaded. Starting workflow processing...")
    gc = connect_to_google_sheet()
    spreadsheet = gc.open(GOOGLE_SHEET_NAME)
    workflow_ws = spreadsheet.worksheet("Workflows")
    outputs_ws = spreadsheet.worksheet("Outputs")
    requests_ws = spreadsheet.worksheet("Requests")
    prompts_ws = spreadsheet.worksheet("Prompts")
    models_ws = spreadsheet.worksheet("Models")
    workflow_steps_ws = spreadsheet.worksheet("Workflow Steps")

    workflow_df = pd.DataFrame(workflow_ws.get_all_records())
    outputs_df = pd.DataFrame(outputs_ws.get_all_records())
    requests_df = pd.DataFrame(requests_ws.get_all_records())
    prompts_df = pd.DataFrame(prompts_ws.get_all_records())
    models_df = pd.DataFrame(models_ws.get_all_records())
    workflow_steps_df = pd.DataFrame(workflow_steps_ws.get_all_records())

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

    # Parse workflow code step (e.g. P2&R1M8)
    def parse_step(step, prev_outputs, custom_topic):
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
        for part in parts:
            if part.startswith('P'):
                prompt_id = part[1:]
                input_text += get_prompt_desc(prompt_id) or ''
            elif part.startswith('R'):
                resp_idx = int(part[1:]) - 1
                if 0 <= resp_idx < len(prev_outputs):
                    input_text += prev_outputs[resp_idx]
            elif part == 'C':
                input_text += custom_topic or ''
        return input_text, model_override, model_id_override

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
        prev_outputs = []
        workflow_steps_records = []
        output_record = {
            'Output ID': get_next_output_id(),
            'Triggered Date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        for i, step in enumerate(steps):
            # Parse the step for prompt, model override, and model ID override
            input_text, model_override, model_id_override = parse_step(step, prev_outputs, custom_topic)
            if model_override and model_id_override:
                model_to_use = model_override
                web_search_enabled = get_model_web_search_by_id(model_id_override)
            else:
                model_to_use = default_model
                web_search_enabled = get_model_web_search_by_id(default_model_id)
            print(f"  - Step {i+1}: {step} (Model: {model_to_use}, Web Search: {web_search_enabled})")
            print(f"    Input: {input_text[:100]}{'...' if len(input_text) > 100 else ''}")
            # Fallback for OpenAI client if responses.create is not available
            if web_search_enabled and not hasattr(client, 'responses'):
                msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                log_error(msg)
                response = "[Web search not supported by your OpenAI Python package version]"
            else:
                response = call_openai_model(input_text, model_to_use, web_search=web_search_enabled)
            prev_outputs.append(response)
            output_col_in = f'Output {2*i+1}'
            output_col_out = f'Output {2*i+2}'
            output_record[output_col_in] = input_text
            output_record[output_col_out] = response
            # Log in Workflow Steps
            workflow_steps_records.append([
                get_next_workflow_steps_id() + i,
                output_record['Triggered Date'],
                workflow_id,
                request_id,
                workflow_code,
                step,
                input_text,
                response,
                "API Response Successfully Returned" if response else "API Error"
            ])
        # Write to Outputs tab
        def to_native(val):
            if hasattr(val, 'item'):
                return val.item()
            if isinstance(val, (int, float, str)) or val is None:
                return val
            return str(val)

        output_row = [to_native(output_record.get(col, '')) for col in outputs_df.columns]
        outputs_ws.append_row(output_row)
        # Write to Workflow Steps tab
        for ws_row in workflow_steps_records:
            ws_row_native = [to_native(x) for x in ws_row]
            workflow_steps_ws.append_row(ws_row_native)
        # Mark request as processed (disabled per user request)
        # requests_ws.update_cell(req_idx + 2, requests_df.columns.get_loc('Active') + 1, 'N')
        print(f"✅ Request {request_id} processed and logged.")
