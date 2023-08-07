# Ensure the correct python version is used.
python="./.env3.11/bin/python"

default:
	$(python) -m build

publish: default
	$(python) -m twine upload dist/*
