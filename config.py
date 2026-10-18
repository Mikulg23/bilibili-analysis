import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
MODELS_DIR = BASE_DIR / "models"
SPARK_JAVA_HOME = os.getenv("SPARK_JAVA_HOME", "")
MYSQL_JDBC_JAR = Path(os.getenv("MYSQL_JDBC_JAR") or str(BASE_DIR / "jars" / "mysql-connector-j-8.4.0.jar"))
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "bilibili_analysis")
HDFS_WEBHDFS_URL = os.getenv("HDFS_WEBHDFS_URL", "").rstrip("/")
HDFS_USER = os.getenv("HDFS_USER", "")
HDFS_DATA_DIR = os.getenv("HDFS_DATA_DIR", "/bilibili-analysis/processed")
CHROME_BINARY = os.getenv("CHROME_BINARY", "")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "")
CRAWLER_HEADLESS = os.getenv("CRAWLER_HEADLESS", "true").lower() == "true"
CRAWLER_WAIT_SECONDS = int(os.getenv("CRAWLER_WAIT_SECONDS", "30"))
CRAWLER_DELAY_MIN = float(os.getenv("CRAWLER_DELAY_MIN", "2"))
CRAWLER_DELAY_MAX = float(os.getenv("CRAWLER_DELAY_MAX", "4"))
