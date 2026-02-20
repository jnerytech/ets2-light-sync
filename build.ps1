# Generate icon
.\.venv\Scripts\python.exe create_icon.py

# Build exe
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m PyInstaller --onedir --windowed --name ETS2LightSync --icon app\icon.ico main_gui.py
