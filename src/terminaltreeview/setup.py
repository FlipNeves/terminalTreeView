import os
import sys
import shutil
import sysconfig
import subprocess

INIT_LINE = 'ttv-tool init powershell | Out-String | Invoke-Expression'
MARKER = '# terminaltreeview integration'

CMD_SHIM = (
    "@echo off\r\n"
    "rem terminaltreeview integration\r\n"
    'set "TTV_DIR="\r\n'
    "for /f \"delims=\" %%i in ('ttv-tool %*') do set \"TTV_DIR=%%i\"\r\n"
    'if defined TTV_DIR if exist "%TTV_DIR%\\" cd /d "%TTV_DIR%"\r\n'
    'set "TTV_DIR="\r\n'
)


def _get_profile(executable: str) -> str | None:
    """Return the CurrentUserAllHosts profile path for a PowerShell executable."""
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-Command", "$PROFILE.CurrentUserAllHosts"],
            capture_output=True, text=True, check=True,
        )
        path = result.stdout.strip()
        return path or None
    except Exception:
        return None


def _scripts_dir() -> str | None:
    """Directory holding the ttv-tool entry point (already on PATH)."""
    exe = shutil.which("ttv-tool")
    if exe:
        return os.path.dirname(exe)
    try:
        return sysconfig.get_path("scripts")
    except Exception:
        return None


def install_powershell(executable: str, label: str) -> bool:
    profile_path = _get_profile(executable)
    if not profile_path:
        print(f"  [skip] {label}: nao encontrado neste sistema.")
        return False

    try:
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)

        lines = []
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = [
            l for l in lines
            if "ttv-tool init" not in l and MARKER not in l
        ]
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"\n{MARKER}\n{INIT_LINE}\n")

        with open(profile_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"  [ok]   {label}: {profile_path}")
        return True
    except Exception as e:
        print(f"  [erro] {label}: {e}")
        return False


def install_cmd() -> bool:
    scripts_dir = _scripts_dir()
    if not scripts_dir:
        print("  [skip] CMD: nao consegui localizar a pasta de Scripts no PATH.")
        return False
    try:
        os.makedirs(scripts_dir, exist_ok=True)
        bat_path = os.path.join(scripts_dir, "ttv.bat")
        with open(bat_path, "w", encoding="utf-8", newline="") as f:
            f.write(CMD_SHIM)
        print(f"  [ok]   CMD: {bat_path}")
        return True
    except Exception as e:
        print(f"  [erro] CMD: {e}")
        return False


def main():
    print("--- terminaltreeview Setup ---")
    print("Configurando integracao 'ttv' nos shells disponiveis...\n")

    results = []
    results.append(install_powershell("pwsh", "PowerShell 7 (pwsh)"))
    results.append(install_powershell("powershell", "Windows PowerShell 5.1"))
    results.append(install_cmd())

    print()
    if any(results):
        print("Pronto! Reinicie o terminal (ou rode '. $PROFILE' no PowerShell)")
        print("para comecar a usar o comando 'ttv'.")
    else:
        print("Nenhum shell pode ser configurado automaticamente.")
        sys.exit(1)


if __name__ == "__main__":
    main()
