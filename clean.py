import os

OUTPUT_DIR = "output"

if os.path.exists(OUTPUT_DIR):
    for root, dirs, files in os.walk(OUTPUT_DIR, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(OUTPUT_DIR)