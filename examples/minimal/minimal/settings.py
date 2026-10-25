import os

import stk


class Config(stk.Config):
    APP_NAME = os.environ.get("APP_NAME", "Minimal")
