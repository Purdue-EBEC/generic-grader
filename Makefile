# Ensure the correct python version is used.
VENV_PATH="./.env3.11/bin/python"
python=$(shell if [ -x $(VENV_PATH) ]; then echo $(VENV_PATH); else echo python; fi)

default:
	$(python) -m build

publish: default
	$(python) -m twine upload dist/*
