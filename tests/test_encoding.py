from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_ROOT = PROJECT_ROOT / "docs"
MOJIBAKE_CHARS = frozenset("閮妯瀹鍏鍖娑璇鏂")


def iter_markdown_files() -> list[Path]:
    root_markdown = sorted(PROJECT_ROOT.glob("*.md"))
    docs_markdown = sorted(DOCS_ROOT.rglob("*.md"))
    return root_markdown + docs_markdown


class EncodingGuardTests(unittest.TestCase):
    def test_markdown_files_decode_as_utf8(self):
        for path in iter_markdown_files():
            with self.subTest(path=path.relative_to(PROJECT_ROOT).as_posix()):
                data = path.read_bytes()
                data.decode("utf-8")

    def test_markdown_files_do_not_contain_common_mojibake_chars(self):
        for path in iter_markdown_files():
            with self.subTest(path=path.relative_to(PROJECT_ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                offending = sorted(set(text) & MOJIBAKE_CHARS)
                self.assertFalse(
                    offending,
                    f"{path.relative_to(PROJECT_ROOT)} contains mojibake-like chars: {''.join(offending)}",
                )

    def test_markdown_files_do_not_contain_replacement_character(self):
        for path in iter_markdown_files():
            with self.subTest(path=path.relative_to(PROJECT_ROOT).as_posix()):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(
                    "\uFFFD",
                    text,
                    f"{path.relative_to(PROJECT_ROOT)} contains Unicode replacement character",
                )
