import os
import sys
import shutil
import sysconfig
import subprocess

BLOCK_BEGIN = "# >>> terminaltreeview >>>"
BLOCK_END = "# <<< terminaltreeview <<<"

LEGACY_MARKERS = ("ttv-tool init", "# terminaltreeview integration")

PS_FUNCTION = """function ttv {
    $ttvEncoding = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $target = ttv-tool @args | Select-Object -Last 1
    } finally {
        [Console]::OutputEncoding = $ttvEncoding
    }
    if ($target) {
        $target = "$target".Trim()
        if ($target -and (Test-Path -LiteralPath $target -PathType Container)) {
            Set-Location -LiteralPath $target
        }
    }
}"""

PS_BLOCK = (
    f"{BLOCK_BEGIN}\n"
    "# Managed by 'ttv-setup'. Run 'ttv-setup --uninstall' to remove.\n"
    f"{PS_FUNCTION}\n"
    f"{BLOCK_END}\n"
)

CMD_SHIM = (
    "@echo off\r\n"
    "rem terminaltreeview integration\r\n"
    'set "TTV_DIR="\r\n'
    "for /f \"delims=\" %%i in ('ttv-tool %*') do set \"TTV_DIR=%%i\"\r\n"
    'if defined TTV_DIR if exist "%TTV_DIR%\\" cd /d "%TTV_DIR%"\r\n'
    'set "TTV_DIR="\r\n'
)


def strip_managed_block(content: str) -> str:
    """Remove the managed ttv block and any legacy integration lines."""
    lines = content.splitlines(keepends=True)
    result = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if stripped == BLOCK_BEGIN:
            in_block = True
            continue
        if stripped == BLOCK_END:
            in_block = False
            continue
        if in_block:
            continue
        if any(marker in line for marker in LEGACY_MARKERS):
            continue
        result.append(line)
    text = "".join(result)
    return text.rstrip("\n") + "\n" if text.strip() else ""


def apply_managed_block(content: str) -> str:
    """Return profile content with exactly one up-to-date ttv block at the end."""
    cleaned = strip_managed_block(content)
    if cleaned:
        return f"{cleaned}\n{PS_BLOCK}"
    return PS_BLOCK


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


def _read_profile(profile_path: str) -> str:
    if not os.path.exists(profile_path):
        return ""
    with open(profile_path, "r", encoding="utf-8") as f:
        return f.read()


def install_powershell(executable: str, label: str) -> bool:
    profile_path = _get_profile(executable)
    if not profile_path:
        print(f"  [skip] {label}: nao encontrado neste sistema.")
        return False

    try:
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)
        content = _read_profile(profile_path)
        new_content = apply_managed_block(content)
        if new_content == content:
            print(f"  [ok]   {label}: ja configurado ({profile_path})")
            return True
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  [ok]   {label}: funcao 'ttv' adicionada em {profile_path}")
        return True
    except Exception as e:
        print(f"  [erro] {label}: {e}")
        return False


def uninstall_powershell(executable: str, label: str) -> bool:
    profile_path = _get_profile(executable)
    if not profile_path or not os.path.exists(profile_path):
        print(f"  [skip] {label}: nada para remover.")
        return False
    try:
        content = _read_profile(profile_path)
        new_content = strip_managed_block(content)
        if new_content == content:
            print(f"  [skip] {label}: nada para remover.")
            return False
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"  [ok]   {label}: integracao removida de {profile_path}")
        return True
    except Exception as e:
        print(f"  [erro] {label}: {e}")
        return False


def _bat_path() -> str | None:
    scripts_dir = _scripts_dir()
    if not scripts_dir:
        return None
    return os.path.join(scripts_dir, "ttv.bat")


def install_cmd() -> bool:
    bat_path = _bat_path()
    if not bat_path:
        print("  [skip] CMD: nao consegui localizar a pasta de Scripts no PATH.")
        return False
    try:
        os.makedirs(os.path.dirname(bat_path), exist_ok=True)
        with open(bat_path, "w", encoding="utf-8", newline="") as f:
            f.write(CMD_SHIM)
        print(f"  [ok]   CMD: shim criado em {bat_path}")
        return True
    except Exception as e:
        print(f"  [erro] CMD: {e}")
        return False


def uninstall_cmd() -> bool:
    bat_path = _bat_path()
    if not bat_path or not os.path.exists(bat_path):
        print("  [skip] CMD: nada para remover.")
        return False
    try:
        os.remove(bat_path)
        print(f"  [ok]   CMD: {bat_path} removido")
        return True
    except Exception as e:
        print(f"  [erro] CMD: {e}")
        return False


def main():
    uninstall = any(arg in ("--uninstall", "-u") for arg in sys.argv[1:])

    print("--- terminaltreeview Setup ---")
    if uninstall:
        print("Removendo integracao 'ttv' dos shells configurados...\n")
        results = [
            uninstall_powershell("pwsh", "PowerShell 7 (pwsh)"),
            uninstall_powershell("powershell", "Windows PowerShell 5.1"),
            uninstall_cmd(),
        ]
        print()
        if any(results):
            print("Integracao removida. Reinicie o terminal para aplicar.")
        else:
            print("Nenhuma integracao encontrada para remover.")
        return

    print("Configurando integracao 'ttv' nos shells disponiveis...\n")
    results = [
        install_powershell("pwsh", "PowerShell 7 (pwsh)"),
        install_powershell("powershell", "Windows PowerShell 5.1"),
        install_cmd(),
    ]

    print()
    if any(results):
        if shutil.which("ttv-tool") is None:
            print("Aviso: 'ttv-tool' nao esta no PATH, entao a funcao 'ttv' ainda nao vai funcionar.")
            print("  Adicione a pasta Scripts do Python ao PATH ou instale com 'pipx install terminaltreeview'.")
            print()
        print("Pronto! O que foi instalado:")
        print(f"  - Perfis do PowerShell: bloco '{BLOCK_BEGIN}' com a funcao 'ttv'")
        print("    (codigo estatico e legivel, sem Invoke-Expression).")
        print("  - CMD: shim 'ttv.bat' na pasta de Scripts do Python.")
        print()
        print("Reinicie o terminal (ou rode '. $PROFILE' no PowerShell)")
        print("para comecar a usar o comando 'ttv'.")
        print("Para desfazer tudo: ttv-setup --uninstall")
    else:
        print("Nenhum shell pode ser configurado automaticamente.")
        sys.exit(1)


if __name__ == "__main__":
    main()
