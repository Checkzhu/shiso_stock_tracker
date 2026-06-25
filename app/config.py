"""项目配置"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'stock_tracker.db')}")
REPORTS_DIR = os.getenv("REPORTS_DIR", os.path.join(BASE_DIR, "reports"))
SOURCE_DIR = os.getenv("SOURCE_DIR", r"D:\学习\股市")

os.makedirs(REPORTS_DIR, exist_ok=True)
data_dir = os.path.join(BASE_DIR, "data")
os.makedirs(data_dir, exist_ok=True)