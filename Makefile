# Ensure the correct python version is used.
python="./.env3.11/bin/python"

default:
	$(python) -m build

publish:
	$(python) -m build && $(python) -m twine upload dist/*
