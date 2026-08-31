import base64
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
IDENTITY_MODULE = REPOSITORY_ROOT / "app" / "js" / "progress-identity.js"


@unittest.skipUnless(shutil.which("node"), "Node.js is required for browser-helper tests")
class ProgressIdentityTests(unittest.TestCase):
    def run_module_assertions(self, assertions: str) -> None:
        encoded = base64.b64encode(IDENTITY_MODULE.read_bytes()).decode("ascii")
        script = textwrap.dedent(
            f"""
            import * as identity from 'data:text/javascript;base64,{encoded}';
            {assertions}
            """
        )
        subprocess.run(
            [shutil.which("node"), "--input-type=module", "--eval", script],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_historical_lyrics_id_matches_current_speech_surface(self) -> None:
        self.run_module_assertions(
            """
            const progress = {
                es1d6ffed1a: {
                    word: 'que', language: 'spanish', correct: 3, wrong: 0,
                    lastCorrect: '2026-08-30T10:00:00.000Z',
                    lastSeen: '2026-08-30T10:00:00.000Z', srsStage: 2
                },
                pt1legacy: { word: 'que', language: 'portuguese', correct: 9, wrong: 0 }
            };
            const surfaceById = new Map([['es0b528b569', 'que']]);
            const records = identity.matchingProgressRecords(progress, {
                fullId: 'es0b528b569', language: 'spanish', surfaceById
            });
            if (records.length !== 1 || records[0].id !== 'es1d6ffed1a') {
                throw new Error('Lyrics history did not bridge to the Speech surface');
            }
            const merged = identity.mergeProgressRecords(records);
            if (merged.word !== 'que' || merged.correct !== 3 || merged.srsStage !== 2) {
                throw new Error('Merged history lost the historical Lyrics answer');
            }
            """
        )

    def test_alias_rows_merge_counts_but_newest_answer_owns_review_stage(self) -> None:
        self.run_module_assertions(
            """
            const records = [
                { id: 'es1old', progress: {
                    word: 'qué', language: 'spanish', correct: 4, wrong: 0,
                    lastCorrect: '2026-08-29T10:00:00.000Z',
                    lastSeen: '2026-08-29T10:00:00.000Z', srsStage: 4
                }},
                { id: 'es0current', progress: {
                    word: 'qué', language: 'spanish', correct: 0, wrong: 1,
                    lastWrong: '2026-08-30T10:00:00.000Z',
                    lastSeen: '2026-08-30T10:00:00.000Z', srsStage: 0
                }}
            ];
            const merged = identity.mergeProgressRecords(records);
            if (merged.correct !== 4 || merged.wrong !== 1) {
                throw new Error('Lifetime counts were not preserved');
            }
            if (merged.lastWrong !== '2026-08-30T10:00:00.000Z' || merged.srsStage !== 0) {
                throw new Error('Newest answer did not own the current review state');
            }
            """
        )


if __name__ == "__main__":
    unittest.main()
