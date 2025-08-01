#!/usr/bin/env python3
"""
AI Podcast Agent Launcher
Simple script to start the agent with proper environment setup.
"""

import sys
import os
from pathlib import Path

def check_requirements():
    """Check if required files and environment variables are present."""
    required_files = [
        'jmio-google-api.json',
        '.env'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   • {file}")
        print("\nPlease ensure these files are in the current directory.")
        return False
    
    # Check environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    required_env_vars = ['SHARE_SHEET_WITH_EMAIL']
    missing_env_vars = []
    
    for var in required_env_vars:
        if not os.getenv(var):
            missing_env_vars.append(var)
    
    if missing_env_vars:
        print("❌ Missing required environment variables:")
        for var in missing_env_vars:
            print(f"   • {var}")
        print("\nPlease check your .env file.")
        return False
    
    return True

def install_dependencies():
    """Install required dependencies if needed."""
    try:
        import gspread
        import google.cloud.storage
        import googleapiclient.discovery
    except ImportError as e:
        print(f"❌ Missing required dependency: {e}")
        print("\nTo install dependencies, run:")
        print("   pip install -r agent_requirements.txt")
        return False
    
    return True

def main():
    """Main launcher function."""
    print("🚀 Starting AI Podcast Agent...")
    
    # Check dependencies
    if not install_dependencies():
        sys.exit(1)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Import and start the agent
    try:
        from ai_agent import PodcastAgent
        
        agent = PodcastAgent()
        
        print("🤖 AI Podcast Agent initialized successfully!")
        print("\n" + "="*50)
        print("AVAILABLE COMMANDS:")
        print("• 'upload latest podcast' - Transfer latest podcast to Google Drive")
        print("• 'help' - Show detailed help")
        print("• 'quit' - Exit the agent")
        print("="*50 + "\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if user_input:
                    response = agent.handle_message(user_input)
                    print(f"\nAgent: {response}\n")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error processing request: {e}")
    
    except Exception as e:
        print(f"❌ Failed to start agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 