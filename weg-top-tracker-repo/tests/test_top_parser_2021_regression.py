import sys
from pathlib import Path
import unittest


# Allow importing `wegtop` without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from wegtop.top_parser import parse_tops_from_corpus  # noqa: E402


class TestTopParser2021Regression(unittest.TestCase):
    def test_normalizes_subtops_and_repairs_run_together(self) -> None:
        """
        Regression for 2021-style OCR artifacts:
          - "TOP 6 2" should be parsed as TOP "6.2"
          - "TOP 17,1" should be parsed as TOP "17.1"
          - "TOP 21" should be repaired to TOP "2.1" (run-together) in the presence of TOP 2
        """
        corpus = {
            "source_path": "Protokoll Eigentümerversammlung vom 26.10.2021.pdf",
            "pages": [
                {
                    "page_index": 0,
                    "text": (
                        "Protokoll Eigentümerversammlung vom 26.10.2021\n\n"
                        "TOP 2 Formalia\n"
                        "Der Versammlungsleiter stellt fest ...\n\n"
                        "TOP 21 Wirtschaftsplan 2022\n"  # OCR run-together for TOP 2.1
                        "Ja-Stimmen: 120 Nein-Stimmen: 0 Enthaltungen: 0\n"
                        "wird beschlossen\n\n"
                        "TOP 6 2 Bestellung Verwalter\n"  # OCR space subpoint
                        "Ja-Stimmen: 100 Nein-Stimmen: 10 Enthaltungen: 10\n"
                        "mehrheitlich beschlossen\n\n"
                        "TOP 17,1 Genehmigung Jahresabrechnung\n"  # OCR comma subpoint
                        "Ja-Stimmen: 90 Nein-Stimmen: 20 Enthaltungen: 10\n"
                        "Beschluss gefasst\n"
                    ),
                }
            ],
        }

        parsed = parse_tops_from_corpus(corpus)
        tops = {r.top_number for r in parsed}

        self.assertIn("2.1", tops)
        self.assertIn("6.2", tops)
        self.assertIn("17.1", tops)
        self.assertNotIn("21", tops)


if __name__ == "__main__":
    unittest.main()

