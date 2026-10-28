import os

from dotenv import load_dotenv


load_dotenv(
    dotenv_path=os.getenv("ENV_FILE", ".env"),
    override=True,
)

ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069").rstrip("/")
ODOO_DB = os.getenv("ODOO_DB", "It_Helpdesk_v2")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")
ODOO_PROJECT_ID = int(os.getenv("ODOO_PROJECT_ID", "1"))
ODOO_FAQ_PUBLIC_CATEGORY_ID = os.getenv("ODOO_FAQ_PUBLIC_CATEGORY_ID")
ODOO_FAQ_DRAFT_CATEGORY_ID = os.getenv("ODOO_FAQ_DRAFT_CATEGORY_ID")
ODOO_FAQ_WRITE_ENABLED = os.getenv(
    "ODOO_FAQ_WRITE_ENABLED", "false"
).lower() in {"1", "true", "yes"}
