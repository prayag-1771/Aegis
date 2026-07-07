# 🔧 shared/

Small utilities and mock data used across modules. **Change rarely** — edits here can affect
everyone, so coordinate before modifying.

## Contents
- **`validate_contract.py`** — validate any module's JSON output against its schema in
  `../contracts/`. Run before every hand-off. `pip install jsonschema` first.
  ```bash
  python shared/validate_contract.py --check-samples          # smoke test
  python shared/validate_contract.py graph my_output.json     # validate your output
  ```
- **`mock_data/`** — shared mock payloads for the command centre to develop against beyond the
  single `contracts/samples/`. Add more scam/note/ring examples here as needed.
