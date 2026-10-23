from terminaltreeview.setup import (
    BLOCK_BEGIN,
    BLOCK_END,
    PS_FUNCTION,
    apply_managed_block,
    strip_managed_block,
)

LEGACY_PROFILE = (
    "Set-Alias ll Get-ChildItem\n"
    "\n"
    "# terminaltreeview integration\n"
    "ttv-tool init powershell | Out-String | Invoke-Expression\n"
)


def test_apply_on_empty_profile():
    result = apply_managed_block("")
    assert result.startswith(BLOCK_BEGIN)
    assert result.rstrip("\n").endswith(BLOCK_END)
    assert "function ttv" in result
    assert "Invoke-Expression" not in result


def test_apply_preserves_user_content():
    result = apply_managed_block("Set-Alias ll Get-ChildItem\n")
    assert "Set-Alias ll Get-ChildItem" in result
    assert BLOCK_BEGIN in result


def test_apply_is_idempotent():
    once = apply_managed_block("Set-Alias ll Get-ChildItem\n")
    twice = apply_managed_block(once)
    assert once == twice
    assert twice.count(BLOCK_BEGIN) == 1


def test_apply_migrates_legacy_invoke_expression():
    result = apply_managed_block(LEGACY_PROFILE)
    assert "Invoke-Expression" not in result
    assert "# terminaltreeview integration" not in result
    assert "Set-Alias ll Get-ChildItem" in result
    assert "function ttv" in result


def test_strip_removes_block_and_legacy_lines():
    installed = apply_managed_block(LEGACY_PROFILE)
    stripped = strip_managed_block(installed)
    assert BLOCK_BEGIN not in stripped
    assert "function ttv" not in stripped
    assert "Invoke-Expression" not in stripped
    assert "Set-Alias ll Get-ChildItem" in stripped


def test_strip_on_profile_with_only_block_returns_empty():
    installed = apply_managed_block("")
    assert strip_managed_block(installed) == ""


def test_function_reads_ttv_output_as_utf8_and_restores_encoding():
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in PS_FUNCTION
    assert "finally" in PS_FUNCTION
    assert "[Console]::OutputEncoding = $ttvEncoding" in PS_FUNCTION
