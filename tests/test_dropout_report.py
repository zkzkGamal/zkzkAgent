from benchmark.dropout import CASES, recovery_steps, result_label


def test_eighteen_cases_with_unique_ids():
    assert len(CASES) == 18
    assert len({c.id for c in CASES}) == 18


def test_recovery_steps_counts_kept_and_redone():
    tool = lambda name, arg: {"type": "tool", "name": name, "input": arg, "ok": True}
    timeline = [
        tool("create_project_folder", "calc"), tool("write_file", "app.py"),
        {"type": "model", "model": "nosana", "ok": False},
        {"type": "user", "text": "retry"},
        tool("write_file", "app.py"), tool("write_file", "index.html"),
    ]
    assert recovery_steps(timeline) == (2, 1)
    assert recovery_steps(timeline[:2]) == (2, 0)


def test_result_label_for_a_clean_stop():
    row = {"turns": [{"ok": True}, {"ok": True}], "interruptions": 1, "replies": ["continue"],
           "cut_happened": True, "success": True}
    assert result_label(row) == "stopped → continue → ✅ passed"
    crashed = {"turns": [{"ok": False, "error": "ReadError: drop"}], "cut_happened": True}
    assert result_label(crashed).startswith("✖ crashed: ReadError")
