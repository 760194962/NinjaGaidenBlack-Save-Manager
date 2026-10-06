import os, sys

os.environ["NGB_LANG"] = "zh"    # tests assert on the Chinese report text
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
