"""`python -m omniread.pipelines.importing` 入口。

单独放 `__main__.py` 而不是直接跑 `importer` 模块：包的 `__init__` 已经导入了
`importer`，再以 `-m ...importer` 执行会让同一模块被导入两次（runpy 会告警）。
"""

from __future__ import annotations

import sys

from omniread.pipelines.importing.importer import main

if __name__ == "__main__":
    sys.exit(main())
