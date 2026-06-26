from __future__ import annotations

import uvicorn

from tgapp.config import AppConfig
from tgapp.web.app import create_app


def main() -> None:
    config = AppConfig.from_env()
    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        reload=config.debug,
    )


if __name__ == "__main__":
    main()
