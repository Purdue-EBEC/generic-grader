sudo apt-get update && sudo apt-get install -y tesseract-ocr

# Install pre-commit hooks
pre-commit install

# Install this package and its dependencies in editable mode
pip3 install --upgrade pip
pip3 install -e .[dev]
