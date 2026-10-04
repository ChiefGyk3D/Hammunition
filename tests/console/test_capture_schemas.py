# SPDX-FileCopyrightText: Copyright (C) 2026 Renegade Penguin LLC
# SPDX-License-Identifier: GPL-3.0-or-later
from .capture_fixtures import extract_schemas

MD = """### status

text

| field | type |

<details><summary>JSON Schema</summary>

```json
{"title": "StatusDocument", "type": "object", "properties": {}, "required": []}
```

</details>

### unit

```json
{"title": "UnitDocument", "type": "object"}
```
"""


def test_extract_schemas_maps_each_kind_to_its_first_json_block() -> None:
    schemas = extract_schemas(MD)
    assert schemas["status"]["title"] == "StatusDocument"
    assert schemas["unit"]["title"] == "UnitDocument"
