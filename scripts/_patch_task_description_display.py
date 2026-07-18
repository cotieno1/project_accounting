import re
from pathlib import Path

root = Path("templates")
patterns = [
    (re.compile(r"\{\{\s*active_task\.description\s*\}\}"), "{{ active_task.description|clean_task_description }}"),
    (re.compile(r"\{\{\s*task\.description\s*\}\}"), "{{ task.description|clean_task_description }}"),
    (re.compile(r"\{\{\s*row\.task\.description\s*\}\}"), "{{ row.task.description|clean_task_description }}"),
    (re.compile(r"active_task\.description\|truncatechars:"), "active_task.description|clean_task_description|truncatechars:"),
    (re.compile(r"(?<!\|clean_task_description\|)task\.description\|truncatechars:"), "task.description|clean_task_description|truncatechars:"),
    (re.compile(r"t\.description\|truncatechars:"), "t.description|clean_task_description|truncatechars:"),
    (re.compile(r"\{\{\s*t\.description\s*\}\}"), "{{ t.description|clean_task_description }}"),
    (re.compile(r'title="\{\{\s*active_task\.description\s*\}\}"'), 'title="{{ active_task.description|clean_task_description }}"'),
]
skip = {"patched view function test.py"}
for path in root.rglob("*.html"):
    if path.name in skip:
        continue
    text = path.read_text(encoding="utf-8")
    orig = text
    for rx, repl in patterns:
        text = rx.sub(repl, text)
    if "clean_task_description|clean_task_description" in text:
        text = text.replace("|clean_task_description|clean_task_description", "|clean_task_description")
    if text != orig:
        if "clean_task_description" in text and "load pioneer_tags" not in text and "load bom_builder_tags" not in text:
            if "{% load static %}" in text:
                text = text.replace("{% load static %}", "{% load static %}\n{% load pioneer_tags %}", 1)
            else:
                text = "{% load pioneer_tags %}\n" + text
        path.write_text(text, encoding="utf-8")
        print("updated", path)
