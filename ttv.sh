ttv() {
    local new_dir
    new_dir=$(python C:/Users/PC/source/person_repos/terminalTreeView/src/terminaltreeview/app.py)
    if [ -n "$new_dir" ] && [ -d "$new_dir" ]; then
        cd "$new_dir"
    fi
}
