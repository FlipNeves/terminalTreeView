import os
import sys
import subprocess

def get_powershell_profile():
    try:
        # Get the current user's profile path
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "$PROFILE"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def main():
    print("--- terminaltreeview Setup ---")
    profile_path = get_powershell_profile()
    
    if not profile_path:
        print("Error: Could not determine PowerShell profile path.")
        sys.exit(1)

    print(f"Detected PowerShell Profile: {profile_path}")
    
    # Ensure profile directory exists
    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
    
    # Create the line to add
    init_line = 'ttv-tool init powershell | Invoke-Expression'
    
    # Check if already present
    already_present = False
    if os.path.exists(profile_path):
        with open(profile_path, 'r', encoding='utf-8') as f:
            if init_line in f.read():
                already_present = True

    if already_present:
        print("Setup already performed! The 'ttv' command should be available in your PowerShell.")
    else:
        try:
            with open(profile_path, 'a', encoding='utf-8') as f:
                f.write(f"\n# terminaltreeview integration\n{init_line}\n")
            print("Successfully added terminaltreeview to your PowerShell profile.")
            print("Please restart your terminal or run: . $PROFILE")
        except Exception as e:
            print(f"Error writing to profile: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
