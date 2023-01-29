import os
import megling
from dotenv import load_dotenv

load_dotenv(dotenv_path = "config")

def getToken():
    return os.getenv("BOT_TOKEN")

def getPrefix():
    return os.getenv("BOT_PREFIX")

def getVersion():
    return os.getenv("BOT_VERSION")

def getTestServerId():
    return int(os.getenv("TESTSERVER_ID"))

def getPath():
    return os.getcwd()