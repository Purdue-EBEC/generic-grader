sudo apt-get update && sudo apt-get install -y tesseract-ocr ranger

alias r='. ranger'

# Install Python dependencies
pip3 install --upgrade pip
# pip3 install --user -r requirements.txt

# Install pre-commit hooks
pre-commit install

# Install this package in editable mode
pip3 install -e .[dev]
