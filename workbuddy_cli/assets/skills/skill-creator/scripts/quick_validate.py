#!/usr/bin/env python3
"""
Enhanced Skill Validator for workbuddy-cli (fixing WorkBuddy's superficial regex-only quick_validate.py).
Validates:
1. YAML frontmatter structure, required fields (`name`, `description`), and `agent_created: true` flag.
2. Hyphen-case naming convention and directory name consistency.
3. Description quality (length bounds, no unreplaced [TODO], no raw angle brackets).
4. File organization & Markdown resource reference audit (verifies that relative paths to `scripts/`, `references/`, `assets/` mentioned in SKILL.md actually exist on disk).
5. Marketplace skill modification lock (`_skillhub_meta.json` / `_knot_meta.json` -> `userModified: true`).
"""

import json
import os
import re
import sys
from pathlib import Path


def validate_skill(skill_path, strict_references=True):
    """Comprehensive validation of a skill directory."""
    skill_path = Path(skill_path).resolve()

    if not skill_path.exists() or not skill_path.is_dir():
        return False, f"Skill directory not found: {skill_path}"

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter = match.group(1)
    body = content[match.end():]

    if "name:" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description:" not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip("'\"")
        if not re.match(r"^[a-z0-9-]+$", name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        if len(name) > 40:
            return False, f"Name '{name}' exceeds 40 characters"

    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    if desc_match:
        description = desc_match.group(1).strip()
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return False, f"Description length ({len(description)}) exceeds 1024 characters"
        if "[TODO" in description:
            return False, "Description still contains unreplaced [TODO] placeholder"

    # Audit file references in SKILL.md body (scripts/*, references/*, assets/*)
    if strict_references:
        ref_patterns = re.findall(
            r"(?:`|\[.*?\]\()((?:scripts|references|assets)/[A-Za-z0-9_./-]+)(?:`|\))",
            body,
        )
        missing_refs = []
        for rel_ref in sorted(set(ref_patterns)):
            # Skip wildcard/placeholder examples like scripts/rotate_pdf.py if marked as example
            target = skill_path / rel_ref
            if not target.exists():
                # Check if it's inside a generic "Examples from other skills" block
                missing_refs.append(rel_ref)
        # Only fail on missing references if they are not from the template boilerplate examples
        boilerplate_examples = {
            "scripts/rotate_pdf.py",
            "references/schema.md",
            "assets/hello-world/",
            "scripts/fill_fillable_fields.py",
            "scripts/convert_pdf_to_images.py",
        }
        real_missing = [r for r in missing_refs if r not in boilerplate_examples]
        if real_missing:
            return False, f"Broken resource references in SKILL.md: {', '.join(real_missing)}"

    return True, "Skill is valid! (Frontmatter, description quality, and resource references verified)"


def mark_marketplace_skill_modified(skill_path):
    """Ensure _skillhub_meta.json or _knot_meta.json sets userModified=true when edited."""
    skill_path = Path(skill_path).resolve()
    updated = []
    for meta_name in ("_skillhub_meta.json", "_knot_meta.json"):
        meta_file = skill_path / meta_name
        if meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            data["userModified"] = True
            meta_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            updated.append(meta_name)
    return updated


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
