import os

import requests
from dotenv import load_dotenv

load_dotenv()

HA_URL = os.getenv("HA_URL", "http://192.168.3.155:8123")
HA_TOKEN = os.getenv("HA_TOKEN")
ENTITY_ID = os.getenv("ENTITY_ID", "light.luz")

if not HA_TOKEN:
    raise ValueError("Missing HA_TOKEN. Set it in .env or environment variables.")

headers = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

def turn_on():
    r = requests.post(
        f"{HA_URL}/api/services/light/turn_on",
        headers=headers,
        json={"entity_id": ENTITY_ID},
        timeout=5,
    )
    print("ON:", r.status_code, r.text)

def turn_off():
    r = requests.post(
        f"{HA_URL}/api/services/light/turn_off",
        headers=headers,
        json={"entity_id": ENTITY_ID},
        timeout=5,
    )
    print("OFF:", r.status_code, r.text)

if __name__ == "__main__":
    turn_on()
    input("Enter para desligar...")
    turn_off()
