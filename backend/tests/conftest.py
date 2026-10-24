"""测试使用临时数据目录（不碰真实数据库）。"""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="zyll-test-"))
