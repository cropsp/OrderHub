import re
import os
import subprocess
import time

def extract_commands(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract bash blocks
    commands = re.findall(r'```bash\n(.*?)\n```', content, re.DOTALL)
    return commands

def main():
    startup_file = "STARTUP.md"
    if not os.path.exists(startup_file):
        print(f"Error: {startup_file} not found.")
        return

    print(f"Reading {startup_file}...")
    blocks = extract_commands(startup_file)
    
    # Identify key commands (naive implementation for demonstration)
    # In a real skill, the agent would use these blocks to run commands via its tools
    for i, block in enumerate(blocks):
        print(f"\n--- Found Command Block {i+1} ---")
        print(block)

    print("\n[Skill Note] The AI Agent will now execute these steps using its terminal tools.")

if __name__ == "__main__":
    main()
