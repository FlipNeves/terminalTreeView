from terminaltreeview.search import match


def score(query, name, mode="fuzzy"):
    result = match(query, name, mode)
    return None if result is None else result[0]


def test_fuzzy_matches_letters_in_order():
    result = match("tst", "test_app.py")
    assert result is not None
    assert [ch for i, ch in enumerate("test_app.py") if i in result[1]] == ["t", "s", "t"]
    assert match("tsx", "test_app.py") is None


def test_contiguous_text_is_highlighted_as_a_block():
    assert match("app", "test_app.py")[1] == [5, 6, 7]


def test_prefers_occurrence_at_word_boundary():
    assert match("app", "happy_app")[1] == [6, 7, 8]


def test_ranking_prefers_exact_then_prefix_then_boundary():
    ranked = sorted(["a_p_p", "happy", "my_app", "apple", "app"], key=lambda name: -score("app", name))
    assert ranked == ["app", "apple", "my_app", "happy", "a_p_p"]


def test_match_ignores_case_and_accents():
    assert match("REL", "relatórios") is not None
    assert match("relatorios", "relatórios")[1] == list(range(10))
    assert match("configuracoes", "Configurações") is not None
    assert match("ó", "relatorios") is not None
    assert match("ó", "relatórios")[1] == [5]


def test_contains_mode_needs_contiguous_text():
    assert match("app", "my_app", "contains") is not None
    assert match("tst", "test", "contains") is None


def test_prefix_mode_needs_start_of_name():
    assert match("my", "my_app", "prefix")[1] == [0, 1]
    assert match("app", "my_app", "prefix") is None


def test_empty_query_matches_everything():
    assert match("", "anything") == (0, [])


def test_length_changing_lowercase_does_not_break_positions():
    result = match("stanbul", "İstanbul")
    assert result is not None
    assert max(result[1]) < len("İstanbul")
