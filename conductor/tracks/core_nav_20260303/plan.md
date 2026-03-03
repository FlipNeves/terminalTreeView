# Implementation Plan: Core Interactive TreeView and 'CD' Shell Integration

## Phase 1: Project Setup and Skeleton [checkpoint: 432b67e]
- [x] Task: Project Scaffolding [cefa14e]
    - [x] Create 'pyproject.toml' or 'requirements.txt' with dependencies (rich, readchar, pytest).
    - [x] Set up basic project structure ('src/', 'tests/').
- [x] Task: Basic TUI Application [c9fff79]
    - [x] Write Tests: Verify a minimal app can start and render.
    - [x] Implement: Create a minimalist Rich-based selection navigator.
- [x] Task: Conductor - User Manual Verification 'Phase 1: Project Setup and Skeleton' (Protocol in workflow.md) [432b67e]

## Phase 2: TreeView Implementation [checkpoint: 6eee268]
- [x] Task: Directory Tree Component [7ac09e3]
    - [x] Write Tests: Verify the tree component correctly lists the contents of a sample directory.
    - [x] Implement: Create custom Rich-based navigator that lists directories.
- [x] Task: Visual Styling (Icons and Colors) [debc60f]
    - [x] Write Tests: Verify icons and colors are correctly applied to different file types.
    - [x] Implement: Add icons and colors for directories and navigation.
- [x] Task: Conductor - User Manual Verification 'Phase 2: TreeView Implementation' (Protocol in workflow.md) [6eee268]

## Phase 3: Directory Traversal and Path Selection
- [x] Task: Selection Logic [780b539]
    - [x] Write Tests: Verify that selecting an item in the tree returns the correct absolute path.
    - [x] Implement: Already implemented in previous step, verified with tests.
- [x] Task: Exit and Output Path [7a2416c]
    - [x] Write Tests: Verify the application exits and prints the selected path to stdout.
    - [x] Implement: Already implemented in previous steps, verified with tests.
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Directory Traversal and Path Selection' (Protocol in workflow.md)

## Phase 4: Shell Integration Wrappers
- [ ] Task: PowerShell Wrapper
    - [ ] Write Tests: Verify a sample PS1 script can execute the tool and change the directory.
    - [ ] Implement: Create 'ttv.ps1' to wrap the Python execution and perform the 'cd' command.
- [ ] Task: CMD Batch Wrapper
    - [ ] Write Tests: Verify a sample .bat file can execute the tool and change the directory.
    - [ ] Implement: Create 'ttv.bat'.
- [ ] Task: Bash/Zsh Function Wrapper
    - [ ] Write Tests: Verify a shell function can execute the tool and change the directory.
    - [ ] Implement: Create a shell function snippet for 'ttv'.
- [ ] Task: Conductor - User Manual Verification 'Phase 4: Shell Integration Wrappers' (Protocol in workflow.md)
