"""Regression tests: full multiline task content must reach the ATLAS planner,
and the role-aware planner must honour explicit role requirements.

These guard the two concepts that must stay distinct:
  * task.content (here: Task.description) = the complete user task / multiline
    instructions — always what the planner consumes.
  * task.title (display) = a short first-line summary for UI/Activity Feed only.

And the planner behaviour: a task explicitly naming SCOUT/FORGE/QA/PULSE (or
asking to involve all specialists) must produce all requested roles, while an
ordinary task with no explicit roles keeps minimal role-aware selection.
"""

from __future__ import annotations

from ai_dev_agent_atlas import planner
from ai_dev_agent_atlas.planner import build_role_aware_plan, _task_text
from ai_dev_agent_core.mock_content import classify_intent
from ai_dev_shared import Task

ALL_FOUR = ("scout", "forge", "qa", "pulse")


def _plan(content: str):
    title = content.split("\n")[0].strip()
    task = Task(title=title, description=content)
    return build_role_aware_plan(task, classify_intent(task))


# ---------------------------------------------------------------------------
# The schema / task model must carry the COMPLETE multi-line content.
# ---------------------------------------------------------------------------


def test_task_model_preserves_complete_multiline_description():
    content = (
        "WAJIB libatkan semua specialist secara berurutan:\n"
        "\n"
        "1. SCOUT riset penyebab bug login.\n"
        "2. FORGE perbaiki bug login.\n"
        "3. QA jalankan test.\n"
        "4. PULSE pantau runtime setelah perbaikan."
    )
    task = Task(title="WAJIB libatkan semua specialist", description=content)
    assert task.description == content


def test_create_task_schema_accepts_multiline_description():
    from ai_dev_api.routes import TaskCreate

    payload = TaskCreate(
        title="WAJIB libatkan semua specialist",
        description=(
            "WAJIB libatkan semua specialist secara berurutan:\n"
            "1. SCOUT riset penyebab bug login.\n"
            "2. FORGE perbaiki bug login.\n"
            "3. QA jalankan test.\n"
            "4. PULSE pantau runtime setelah perbaikan."
        ),
    )
    assert "\n1. SCOUT" in payload.description
    assert len(payload.description.splitlines()) == 5


# ---------------------------------------------------------------------------
# The planner must receive the COMPLETE content (never just the title).
# ---------------------------------------------------------------------------


def test_planner_input_contains_full_content_not_just_title():
    content = (
        "WAJIB libatkan semua specialist secara berurutan:\n"
        "1. SCOUT riset penyebab bug login.\n"
        "2. FORGE perbaiki bug login.\n"
        "3. QA jalankan test.\n"
        "4. PULSE pantau runtime setelah perbaikan."
    )
    task = Task(title="WAJIB libatkan semua specialist", description=content)
    text = _task_text(task)
    assert "\n1. scout" in text
    assert "2. forge" in text
    assert "3. qa" in text
    assert "4. pulse" in text
    # The planner only ever reads task content; a display title alone would
    # NOT contain the per-line role instructions.
    assert "4. pulse" in text


def test_display_title_is_first_line_but_content_is_untouched():
    content = (
        "WAJIB libatkan semua specialist secara berurutan:\n"
        "\n"
        "1. SCOUT ...\n"
        "2. FORGE ...\n"
        "3. QA ...\n"
        "4. PULSE ..."
    )
    display_title = content.split("\n")[0].strip()
    assert display_title == "WAJIB libatkan semua specialist secara berurutan:"
    # The planner still consumes the FULL content, not the short title.
    task = Task(title=display_title, description=content)
    text = _task_text(task)
    assert "4. pulse" in text


# ---------------------------------------------------------------------------
# Explicit role requirements.
# ---------------------------------------------------------------------------


def test_explicit_all_four_via_numbered_list_selects_all():
    content = (
        "WAJIB libatkan semua specialist secara berurutan:\n"
        "1. SCOUT kerjakan bagian pertama.\n"
        "2. FORGE kerjakan bagian kedua.\n"
        "3. QA kerjakan bagian ketiga.\n"
        "4. PULSE kerjakan bagian keempat."
    )
    plan = _plan(content)
    assert plan.agents == ALL_FOUR


def test_explicit_all_four_via_role_chain_selects_all():
    plan = _plan("SCOUT -> FORGE -> QA -> PULSE, lakukan semuanya berurutan.")
    assert plan.agents == ALL_FOUR


def test_ordinary_task_keeps_minimal_selection():
    plan = _plan("fix the frontend login bug so it stops crashing")
    assert plan.agents == ("forge", "qa")


def test_blank_lines_and_numbered_lists_survive():
    content = (
        "Libatkan semua specialist:\n"
        "\n"
        "\n"
        "1. SCOUT riset dulu.\n"
        "2. FORGE implementasi.\n"
        "3. QA uji.\n"
        "4. PULSE pantau.\n"
        "\n"
    )
    text = _task_text(Task(title="Libatkan semua specialist", description=content))
    assert "1. scout" in text
    assert "4. pulse" in text


def test_unicode_bahasa_stays_unchanged():
    content = (
        "Libatkan semua specialist 🔍:\n"
        "SCOUT → telusuri kode sumber dengan hati-hati.\n"
        "FORGE → perbaiki dan jaga kualitas kode.\n"
        "QA → pastikan tidak ada regresi fungsi login mémoir.\n"
        "PULSE → pantau runtime aplikasi."
    )
    task = Task(title="Libatkan semua specialist", description=content)
    # The arrows / accented text / emoji are preserved byte-for-byte.
    assert "→" in task.description
    assert "mémoir" in task.description
    assert "🔍" in task.description
