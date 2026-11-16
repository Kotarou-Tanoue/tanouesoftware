from dotenv import load_dotenv

load_dotenv()

from app.__init__ import create_app

app = create_app()
