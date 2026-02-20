python3 -m venv .venv
source .venv/bin/activate
deactivate
pip install -r requirements.txt
python test_ha_light.py
