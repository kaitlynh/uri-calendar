import os
from pathlib import Path
import json

# --- Configuration ---
SOURCE_DIR_NAME = 'events'  # Change this to your source path
OUTPUT_FILE = 'merge.json'          # Name of the new file

def merge_json_files():
    # 1. Setup paths (Relative to where you run the script)
    current_dir = Path.cwd()
    source_path = current_dir.parent / SOURCE_DIR_NAME
    
    if not source_path.exists():
        print(f"Error: Folder '{SOURCE_DIR_NAME}' not found at {source_path}")
        return

    combined_data = []

    # 2. Iterate through files and load data
    for file_path in sorted(source_path.iterdir()):
        # Only process files (you can add .json filter if needed)
        if file_path.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # If the file contains a list, extend our master list
                    if isinstance(data, list):
                        combined_data.extend(data)
                        print(f"Imported {len(data)} items from {file_path.name}")
                    else:
                        print(f"Skipped {file_path.name}: Content is not a list.")
            except Exception as e:
                print(f"Could not process {file_path.name}: {e}")

    # 3. Save the master list to the new file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=2)

    print(f"\nSuccess! Merged {len(combined_data)} total items into '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    merge_json_files()