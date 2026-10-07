"""Run one audio file through the shared pipeline.  Usage:
    python -m scripts.day2_test clip.ogg ha
"""
import os
import sys

from app.config import Config
from app import db, natlas_client, pipeline

os.makedirs(os.path.dirname(Config.DB_PATH), exist_ok=True)
db.init(Config.DB_PATH)
natlas_client.configure(Config.GATEWAY_URL, Config.GATEWAY_KEY)
res = pipeline.handle_voice(sys.argv[1], sys.argv[2], "USR_00000000", "web", os.path.getsize(sys.argv[1]))
for k, v in res.items():
    print(f"{k:14}: {v}")
