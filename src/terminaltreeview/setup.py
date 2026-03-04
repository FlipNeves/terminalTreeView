import os
import sys
import subprocess

def get_powershell_profile():
    try:
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
    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
    
    init_line = 'ttv-tool init powershell | Out-String | Invoke-Expression'
    
    lines = []
    if os.path.exists(profile_path):
        with open(profile_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    new_lines = [l for l in lines if 'ttv-tool init' not in l and '# terminaltreeview' not in l]
    
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
        
    new_lines.append(f"\n# terminaltreeview integration\n{init_line}\n")

    try:
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print("Successfully updated terminaltreeview in your PowerShell profile.")
        print("Please restart your terminal or run: . $PROFILE")
    except Exception as e:
        print(f"Error writing to profile: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
